# CryptoPro test CA page
class CryptoProLocators:
    # Link: "Generate keys and submit a certificate request"
    CERTRQMA_ASP_LINK = 'a[href="certrqma.asp"]'
    # "Name" field
    IDENTIFICATION_INFO_CERTIFICATE_NAME_FIELD = 'input#locTbCommonName'
    # Test value for the "Name" field
    CERTIFICATE_NAME = "Test Certificate"
    # "Mark key as exportable" checkbox
    ACTIVE_FUNCTION_EXPORT_CHECK = 'input[name="cbMarkKeyExportable"]'
    # "Issue" button
    ISSUE_BUTTON = 'input[name="btnSubmit"]'
    # "Install certificate" link
    INSTALL_CERT = 'span#spnInstall'
    # Text shown by the CryptoPro test CA after certificate installation.
    NEW_CERT_INSTALLED = "\u041d\u043e\u0432\u044b\u0439 \u0441\u0435\u0440\u0442\u0438\u0444\u0438\u043a\u0430\u0442 \u0443\u0441\u043f\u0435\u0448\u043d\u043e \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d."

class URL:
    CRYPTOPRO_URL = 'https://testgost2012.cryptopro.ru/certsrv/'
    CRYPTOPRO_UC_URL = 'https://testgost2012.cryptopro.ru/certsrv/certnew.cer?ReqID=CACert&Renewal=-1&Enc=b64'
