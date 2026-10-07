import pytest

from app.calculator import add, calculate, divide, multiply, subtract


def test_add():
    assert add(10, 5) == 15


def test_subtract():
    assert subtract(10, 5) == 5


def test_multiply():
    assert multiply(10, 5) == 50


def test_divide():
    assert divide(10, 5) == 2


def test_divide_by_zero_raises():
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(10, 0)


def test_calculate_dispatches():
    assert calculate("multiply", 6, 7) == 42


def test_calculate_rejects_unknown_operation():
    with pytest.raises(ValueError, match="Unknown operation"):
        calculate("modulo", 10, 3)
