from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import subprocess
import tempfile


CRYPTCP = Path(os.environ.get("CRYPTCP_PATH", "/opt/cprocsp/bin/amd64/cryptcp"))
CERTMGR = Path(os.environ.get("CERTMGR_PATH", "/opt/cprocsp/bin/amd64/certmgr"))


@dataclass(frozen=True)
class CertificateInfo:
    subject: str
    issuer: str
    serial: str
    thumbprint: str
    display_name: str


@dataclass(frozen=True)
class SignedPdfArtifacts:
    signed_pdf: Path
    cms_signature: Path
    signer: CertificateInfo


def sign_pdf_with_cryptopro(
    source_pdf: Path,
    signed_pdf: Path,
    *,
    certificate_name: str,
    cms_signature: Path | None = None,
    placeholder_size: int = 65536,
) -> SignedPdfArtifacts:
    """Create a visible PDF signature field and fill it with a CryptoPro CMS signature."""
    source_pdf = source_pdf.resolve()
    signed_pdf = signed_pdf.resolve()
    cms_signature = (cms_signature or signed_pdf.with_suffix(".p7s")).resolve()

    signer = find_certificate(certificate_name)
    prepared_pdf, ranges, contents_start, contents_end = build_pdf_with_signature_placeholder(
        source_pdf.read_bytes(),
        signer,
        placeholder_size=placeholder_size,
    )

    data_to_sign = prepared_pdf[ranges[0]:ranges[0] + ranges[1]] + prepared_pdf[ranges[2]:ranges[2] + ranges[3]]

    signed_pdf.parent.mkdir(parents=True, exist_ok=True)
    cms_signature.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdf-pades-") as tmpdir:
        byte_range_file = Path(tmpdir) / "byte-range.bin"
        raw_signature_file = Path(tmpdir) / "signature.p7s"

        byte_range_file.write_bytes(data_to_sign)
        run_cryptcp_detached_signature(byte_range_file, raw_signature_file, signer, certificate_name)
        verify_cryptcp_detached_signature(byte_range_file, raw_signature_file, signer)

        signature = raw_signature_file.read_bytes()
        cms_signature.write_bytes(signature)

    signature_hex = signature.hex().upper().encode("ascii")
    reserved_hex_size = contents_end - contents_start
    if len(signature_hex) > reserved_hex_size:
        raise RuntimeError(
            f"CMS signature does not fit the PDF placeholder: {len(signature_hex)} hex bytes "
            f"for {reserved_hex_size} available bytes. Increase placeholder_size."
        )

    result = bytearray(prepared_pdf)
    result[contents_start:contents_start + len(signature_hex)] = signature_hex

    signed_pdf.write_bytes(bytes(result))
    assert_pdf_signature_structure(signed_pdf)

    return SignedPdfArtifacts(signed_pdf=signed_pdf, cms_signature=cms_signature, signer=signer)


def find_certificate(certificate_name: str) -> CertificateInfo:
    if not CERTMGR.exists():
        raise FileNotFoundError(f"certmgr was not found: {CERTMGR}")

    result = subprocess.run(
        [str(CERTMGR), "-list", "-store", "uMy"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    certs = parse_certmgr_output(result.stdout)
    matching_certs = [
        cert
        for cert in certs
        if certificate_name.lower() in cert.subject.lower()
        or certificate_name.lower() in cert.display_name.lower()
    ]

    if not matching_certs:
        details = result.stdout.strip() or result.stderr.strip() or "store is empty"
        raise RuntimeError(
            f"Certificate '{certificate_name}' was not found in the uMy store.\n{details}"
        )

    return matching_certs[-1]


def parse_certmgr_output(output: str) -> list[CertificateInfo]:
    certs: list[CertificateInfo] = []
    current: dict[str, str] = {}
    current_key: str | None = None

    def flush_current():
        if not current:
            return
        subject = current.get("subject") or current.get("cert subject") or ""
        issuer = current.get("issuer") or ""
        serial = current.get("serial") or current.get("serial number") or ""
        thumbprint = (
            current.get("sha1 hash")
            or current.get("thumbprint")
            or current.get("hash")
            or ""
        )
        display_name = extract_common_name(subject) or subject or "CryptoPro certificate"
        certs.append(
            CertificateInfo(
                subject=subject,
                issuer=issuer,
                serial=serial,
                thumbprint=normalize_thumbprint(thumbprint),
                display_name=display_name,
            )
        )

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^\s*\d+-{3,}\s*$", line):
            flush_current()
            current = {}
            current_key = None
            continue

        if ":" in line:
            key, value = line.split(":", 1)
            normalized_key = key.strip().lower()
            current[normalized_key] = value.strip()
            current_key = normalized_key
        elif current_key and line.startswith((" ", "\t")):
            current[current_key] = f"{current[current_key]} {line.strip()}".strip()

    flush_current()
    return [cert for cert in certs if cert.subject or cert.thumbprint]


def run_cryptcp_detached_signature(
    source_file: Path,
    signature_file: Path,
    signer: CertificateInfo,
    certificate_name: str,
) -> None:
    if not CRYPTCP.exists():
        raise FileNotFoundError(f"cryptcp was not found: {CRYPTCP}")

    csc = ["-thumbprint", signer.thumbprint] if signer.thumbprint else ["-dn", certificate_name]
    pin = os.environ.get("CRYPTOPRO_PIN")

    command = [
        str(CRYPTCP),
        "-sign",
        "-detached",
        "-cert",
        "-errchain",
        "-norev",
        "-nonet",
        *csc,
        "-uMy",
    ]
    if pin:
        command.extend(["-pin", pin])
    command.extend([str(source_file), str(signature_file)])

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        safe_command = ["***" if pin and item == pin else item for item in command]
        raise RuntimeError(
            "CryptoPro cryptcp failed to sign the PDF ByteRange.\n"
            f"Command: {' '.join(safe_command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    if not signature_file.exists() or signature_file.stat().st_size == 0:
        raise RuntimeError(f"cryptcp finished successfully but did not create a signature: {signature_file}")


def verify_cryptcp_detached_signature(source_file: Path, signature_file: Path, signer: CertificateInfo) -> None:
    csc = ["-thumbprint", signer.thumbprint] if signer.thumbprint else ["-verall"]
    command = [
        str(CRYPTCP),
        "-verify",
        "-detached",
        *csc,
        "-uMy",
        "-errchain",
        "-norev",
        "-nonet",
        str(source_file),
        str(signature_file),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "CryptoPro cryptcp failed to verify the detached CMS signature and certificate chain.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def build_pdf_with_signature_placeholder(
    original_pdf: bytes,
    signer: CertificateInfo,
    *,
    placeholder_size: int,
) -> tuple[bytes, list[int], int, int]:
    metadata = parse_pdf_metadata(original_pdf)

    sig_obj = metadata["size"]
    field_obj = sig_obj + 1
    appearance_obj = sig_obj + 2
    acroform_obj = sig_obj + 3
    font_obj = sig_obj + 4
    new_size = sig_obj + 5

    signer_name = pdf_string(signer.display_name)
    signing_time = pdf_date()

    stamp_lines = [
        "Signed by CryptoPro",
        f"Certificate: {clip_text(signer.display_name, 46)}",
        f"Subject: {clip_text(signer.subject or signer.display_name, 58)}",
        f"Serial: {clip_text(signer.serial or '-', 42)}",
        f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    ]

    width = 265
    height = 82
    rect = [300, 160, 565, 242]
    appearance_stream = make_appearance_stream(stamp_lines, width, height)
    contents_placeholder = b"0" * (placeholder_size * 2)
    byte_range_placeholder = b"/ByteRange [0000000000 0000000000 0000000000 0000000000]"

    sig_dict = b"\n".join(
        [
            b"<<",
            b"/Type /Sig",
            b"/Filter /Adobe.PPKLite",
            b"/SubFilter /ETSI.CAdES.detached",
            b"/Name " + signer_name,
            b"/M " + pdf_string(signing_time),
            b"/Reason " + pdf_string("CryptoPro test PDF signature"),
            b"/ContactInfo " + pdf_string("playwright-cryptopro-demo"),
            byte_range_placeholder,
            b"/Contents <" + contents_placeholder + b">",
            b">>",
        ]
    )

    field_dict = (
        f"<<\n"
        f"/Type /Annot\n"
        f"/Subtype /Widget\n"
        f"/FT /Sig\n"
        f"/T (CryptoProSignature)\n"
        f"/F 132\n"
        f"/P {metadata['page_obj']} 0 R\n"
        f"/Rect [{rect[0]} {rect[1]} {rect[2]} {rect[3]}]\n"
        f"/V {sig_obj} 0 R\n"
        f"/AP << /N {appearance_obj} 0 R >>\n"
        f">>"
    ).encode("ascii")

    appearance_dict = (
        f"<<\n"
        f"/Type /XObject\n"
        f"/Subtype /Form\n"
        f"/BBox [0 0 {width} {height}]\n"
        f"/Resources << /Font << /F1 {font_obj} 0 R >> >>\n"
        f"/Length {len(appearance_stream)}\n"
        f">>\n"
        f"stream\n"
    ).encode("ascii") + appearance_stream + b"\nendstream"

    acroform_dict = (
        f"<<\n"
        f"/Fields [{field_obj} 0 R]\n"
        f"/SigFlags 3\n"
        f"/DR << /Font << /F1 {font_obj} 0 R >> >>\n"
        f">>"
    ).encode("ascii")

    font_dict = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    updated_page = append_page_annotation(metadata["page_body"], field_obj)
    updated_root = append_catalog_acroform(metadata["root_body"], acroform_obj)

    objects = [
        (metadata["page_obj"], updated_page),
        (metadata["root_obj"], updated_root),
        (sig_obj, sig_dict),
        (field_obj, field_dict),
        (appearance_obj, appearance_dict),
        (acroform_obj, acroform_dict),
        (font_obj, font_dict),
    ]

    pdf = write_incremental_update(
        original_pdf,
        objects,
        size=new_size,
        root_obj=metadata["root_obj"],
        info_obj=metadata["info_obj"],
        pdf_id=metadata["id"],
        prev_startxref=metadata["startxref"],
    )

    contents_start = pdf.index(b"/Contents <" + contents_placeholder) + len(b"/Contents <")
    contents_end = contents_start + len(contents_placeholder)
    byte_ranges = [0, contents_start, contents_end, len(pdf) - contents_end]
    byte_range_value = (
        f"/ByteRange [{byte_ranges[0]:010d} {byte_ranges[1]:010d} "
        f"{byte_ranges[2]:010d} {byte_ranges[3]:010d}]"
    ).encode("ascii")

    if len(byte_range_value) != len(byte_range_placeholder):
        raise RuntimeError("Internal error: ByteRange placeholder changed its length")

    return pdf.replace(byte_range_placeholder, byte_range_value, 1), byte_ranges, contents_start, contents_end


def parse_pdf_metadata(pdf: bytes) -> dict[str, int | bytes | None]:
    startxref_match = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", pdf, re.S)
    if not startxref_match:
        raise RuntimeError("PDF does not contain startxref")

    trailer_match = re.search(rb"trailer\s*<<(.*?)>>\s*startxref\s+\d+\s+%%EOF\s*$", pdf, re.S)
    if not trailer_match:
        raise RuntimeError("PDF does not contain trailer")

    trailer = trailer_match.group(1)
    size = require_int(trailer, rb"/Size\s+(\d+)", "trailer /Size")
    root_obj = require_int(trailer, rb"/Root\s+(\d+)\s+\d+\s+R", "trailer /Root")
    info_obj = optional_int(trailer, rb"/Info\s+(\d+)\s+\d+\s+R")
    pdf_id_match = re.search(rb"/ID\s*(\[\s*<[^>]+>\s*<[^>]+>\s*\])", trailer, re.S)

    root_body = read_object_body(pdf, root_obj)
    page_obj, page_body = find_first_page(pdf)

    return {
        "startxref": int(startxref_match.group(1)),
        "size": size,
        "root_obj": root_obj,
        "root_body": root_body,
        "page_obj": page_obj,
        "page_body": page_body,
        "info_obj": info_obj,
        "id": pdf_id_match.group(1) if pdf_id_match else None,
    }


def read_object_body(pdf: bytes, obj_num: int) -> bytes:
    pattern = rb"(?m)^" + str(obj_num).encode("ascii") + rb"\s+0\s+obj\s*"
    match = re.search(pattern, pdf)
    if not match:
        raise RuntimeError(f"PDF object {obj_num} 0 obj was not found")

    end = pdf.find(b"endobj", match.end())
    if end == -1:
        raise RuntimeError(f"PDF object {obj_num} 0 obj is not closed")

    return pdf[match.end():end].strip()


def find_first_page(pdf: bytes) -> tuple[int, bytes]:
    for match in re.finditer(rb"(?m)^(\d+)\s+0\s+obj\s*", pdf):
        obj_num = int(match.group(1))
        end = pdf.find(b"endobj", match.end())
        if end == -1:
            continue
        body = pdf[match.end():end].strip()
        if b"/Type /Page" in body and b"/Type /Pages" not in body:
            return obj_num, body
    raise RuntimeError("PDF does not contain a /Type /Page object")


def append_catalog_acroform(root_body: bytes, acroform_obj: int) -> bytes:
    return append_pdf_dict_entry(root_body, b"/AcroForm", f"{acroform_obj} 0 R".encode("ascii"))


def append_page_annotation(page_body: bytes, field_obj: int) -> bytes:
    annots_match = re.search(rb"/Annots\s*\[(.*?)\]", page_body, re.S)
    if annots_match:
        replacement = b"/Annots [" + annots_match.group(1).strip() + f" {field_obj} 0 R".encode("ascii") + b"]"
        return page_body[:annots_match.start()] + replacement + page_body[annots_match.end():]

    return append_pdf_dict_entry(page_body, b"/Annots", f"[{field_obj} 0 R]".encode("ascii"))


def append_pdf_dict_entry(dictionary: bytes, key: bytes, value: bytes) -> bytes:
    if key in dictionary:
        raise RuntimeError(f"PDF dictionary already contains {key.decode('ascii')}; custom handling is required")

    end = dictionary.rfind(b">>")
    if end == -1:
        raise RuntimeError("PDF dictionary is not closed")
    return dictionary[:end].rstrip() + b"\n" + key + b" " + value + b"\n" + dictionary[end:]


def write_incremental_update(
    original_pdf: bytes,
    objects: list[tuple[int, bytes]],
    *,
    size: int,
    root_obj: int,
    info_obj: int | None,
    pdf_id: bytes | None,
    prev_startxref: int,
) -> bytes:
    output = bytearray(original_pdf.rstrip() + b"\n")
    offsets: dict[int, int] = {}

    for obj_num, body in objects:
        offsets[obj_num] = len(output)
        output.extend(f"{obj_num} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(b"xref\n")
    for start, group in consecutive_groups(sorted(offsets)):
        output.extend(f"{start} {len(group)}\n".encode("ascii"))
        for obj_num in group:
            output.extend(f"{offsets[obj_num]:010d} 00000 n \n".encode("ascii"))

    trailer_parts = [
        f"<< /Size {size} /Root {root_obj} 0 R".encode("ascii"),
    ]
    if info_obj is not None:
        trailer_parts.append(f"/Info {info_obj} 0 R".encode("ascii"))
    if pdf_id:
        trailer_parts.append(b"/ID " + pdf_id)
    trailer_parts.append(f"/Prev {prev_startxref} >>".encode("ascii"))

    output.extend(b"trailer\n")
    output.extend(b" ".join(trailer_parts))
    output.extend(b"\nstartxref\n")
    output.extend(str(xref_offset).encode("ascii"))
    output.extend(b"\n%%EOF\n")
    return bytes(output)


def consecutive_groups(numbers: list[int]) -> list[tuple[int, list[int]]]:
    if not numbers:
        return []

    groups: list[tuple[int, list[int]]] = []
    current = [numbers[0]]
    start = numbers[0]

    for number in numbers[1:]:
        if number == current[-1] + 1:
            current.append(number)
            continue
        groups.append((start, current))
        current = [number]
        start = number

    groups.append((start, current))
    return groups


def make_appearance_stream(lines: list[str], width: int, height: int) -> bytes:
    text_commands = []
    y = height - 18
    for index, line in enumerate(lines):
        font_size = 10 if index else 12
        text_commands.append(
            f"BT /F1 {font_size} Tf 1 0 0 1 10 {y} Tm ({escape_pdf_text(line)}) Tj ET"
        )
        y -= 14

    commands = [
        "q",
        "0.96 0.99 0.98 rg",
        f"0 0 {width} {height} re f",
        "0.10 0.48 0.36 RG",
        "1.2 w",
        f"1 1 {width - 2} {height - 2} re S",
        "0.10 0.48 0.36 rg",
        *text_commands,
        "Q",
    ]
    return ("\n".join(commands) + "\n").encode("ascii")


def assert_pdf_signature_structure(signed_pdf: Path) -> None:
    pdf = signed_pdf.read_bytes()
    required_markers = [
        b"/Type /Sig",
        b"/FT /Sig",
        b"/ByteRange [",
        b"/Contents <",
        b"/SubFilter /ETSI.CAdES.detached",
        b"/AP << /N",
    ]
    missing = [marker.decode("ascii") for marker in required_markers if marker not in pdf]
    if missing:
        raise RuntimeError(f"Signed PDF does not contain required markers: {missing}")

    byte_range_match = re.search(rb"/ByteRange \[(\d+) (\d+) (\d+) (\d+)\]", pdf)
    if not byte_range_match:
        raise RuntimeError("Signed PDF does not contain a valid /ByteRange")

    ranges = [int(item) for item in byte_range_match.groups()]
    if ranges[0] != 0 or ranges[1] <= 0 or ranges[2] <= ranges[1] or ranges[3] <= 0:
        raise RuntimeError(f"Invalid /ByteRange: {ranges}")

    contents_match = re.search(rb"/Contents <([0-9A-Fa-f]+)>", pdf)
    if not contents_match or set(contents_match.group(1)) <= {ord("0")}:
        raise RuntimeError("PDF signature /Contents is empty")


def require_int(data: bytes, pattern: bytes, description: str) -> int:
    match = re.search(pattern, data)
    if not match:
        raise RuntimeError(f"PDF does not contain {description}")
    return int(match.group(1))


def optional_int(data: bytes, pattern: bytes) -> int | None:
    match = re.search(pattern, data)
    return int(match.group(1)) if match else None


def extract_common_name(subject: str) -> str:
    match = re.search(r"(?:^|,\s*)CN\s*=\s*([^,]+)", subject)
    return match.group(1).strip() if match else ""


def normalize_thumbprint(value: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", value).upper()


def pdf_date() -> str:
    return datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")


def pdf_string(value: str) -> bytes:
    return f"({escape_pdf_text(value)})".encode("ascii")


def escape_pdf_text(value: str) -> str:
    ascii_value = value.encode("ascii", "replace").decode("ascii")
    return ascii_value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def clip_text(value: str, max_length: int) -> str:
    value = " ".join((value or "").split())
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."
