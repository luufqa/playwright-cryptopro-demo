from locators.cryptopro_locators import CryptoProLocators
from pages.cryptopro_page import CryptoPro
import pytest


@pytest.fixture
def crypto_pro(page):
    return CryptoPro(page)


# Page "CryptoPro test CA"
class TestCryptoPro:
    @pytest.mark.order(1)
    @pytest.mark.sign
    def test_cert(self, crypto_pro):
        """CryptoPro test CA and signing certificates can be installed"""
        # Arrange
        expected_install_status = CryptoProLocators.NEW_CERT_INSTALLED

        # Act
        actual_result_installer = crypto_pro.create_test_certificate()

        # Assert
        assert actual_result_installer == expected_install_status

    @pytest.mark.order(2)
    @pytest.mark.sign
    def test_sign(self, crypto_pro):
        """A PDF can be signed with the generated CryptoPro test certificate"""
        # Arrange

        # Act
        artifacts = crypto_pro.sign()

        # Assert
        assert artifacts["signed_pdf"].exists()
        assert artifacts["signed_pdf"].stat().st_size > 0
        assert artifacts["cms_signature"].exists()
        assert artifacts["cms_signature"].stat().st_size > 0
        assert artifacts["screenshot"].exists()
        assert artifacts["screenshot"].stat().st_size > 0
        assert CryptoProLocators.CERTIFICATE_NAME in artifacts["signer"].display_name
