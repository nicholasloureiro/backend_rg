def validate_cpf(cpf: str) -> bool:
    """
    Validates a Brazilian CPF using the check digit algorithm.
    Expects a string of exactly 11 digits (no formatting).
    Returns True if valid, False otherwise.
    """
    if not cpf or len(cpf) != 11:
        return False

    # Reject known invalid CPFs (all same digit)
    if cpf == cpf[0] * 11:
        return False

    # Validate first check digit
    total = sum(int(cpf[i]) * (10 - i) for i in range(9))
    remainder = total % 11
    first_digit = 0 if remainder < 2 else 11 - remainder
    if int(cpf[9]) != first_digit:
        return False

    # Validate second check digit
    total = sum(int(cpf[i]) * (11 - i) for i in range(10))
    remainder = total % 11
    second_digit = 0 if remainder < 2 else 11 - remainder
    if int(cpf[10]) != second_digit:
        return False

    return True
