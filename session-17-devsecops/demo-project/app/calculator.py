"""Core calculator logic, kept free of any web framework so it is easy to unit test."""


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def multiply(a, b):
    return a * b


def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


OPERATIONS = {
    "add": add,
    "subtract": subtract,
    "multiply": multiply,
    "divide": divide,
}


def calculate(operation, a, b):
    if operation not in OPERATIONS:
        raise ValueError(f"Unknown operation: {operation}")
    return OPERATIONS[operation](a, b)
