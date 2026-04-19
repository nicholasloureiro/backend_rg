"""
Unit tests for the CPF validation utility.

CPF is the Brazilian individual taxpayer ID. The algorithm has two check
digits computed via weighted sums of the preceding digits.
"""
import pytest

from accounts.utils import validate_cpf


class TestValidateCPF:
    @pytest.mark.parametrize("cpf", [
        "52998224725",  # real-world valid example
        "12345678909",  # valid test CPF
        "11144477735",  # valid test CPF
    ])
    def test_valid_cpfs_pass(self, cpf):
        assert validate_cpf(cpf) is True

    @pytest.mark.parametrize("cpf", [
        "00000000000",
        "11111111111",
        "99999999999",
    ])
    def test_all_same_digits_rejected(self, cpf):
        """CPFs with all identical digits are a well-known invalid pattern."""
        assert validate_cpf(cpf) is False

    @pytest.mark.parametrize("cpf", [
        "12345678900",  # wrong check digits
        "52998224724",  # valid except last digit
    ])
    def test_invalid_check_digits_rejected(self, cpf):
        assert validate_cpf(cpf) is False

    @pytest.mark.parametrize("cpf", [
        "",
        "123",
        "1234567890",   # 10 digits
        "123456789012", # 12 digits
    ])
    def test_wrong_length_rejected(self, cpf):
        assert validate_cpf(cpf) is False

    def test_none_rejected(self):
        assert validate_cpf(None) is False
