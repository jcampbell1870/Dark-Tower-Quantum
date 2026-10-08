"""Strict DTL quantum profile and bounded state-vector execution."""

from collections import Counter
from dataclasses import dataclass
import json
import math
import random
import re


MAX_SOURCE_BYTES = 65536
MAX_QUBITS = 12
MAX_OPERATIONS = 512
MAX_SHOTS = 8192


class TowerError(ValueError):
    pass


@dataclass(frozen=True)
class Program:
    qubits: int
    operations: tuple[tuple[str, tuple[int, ...]], ...]
    messages: tuple[str, ...]


TOKEN = re.compile(
    r'\s+|//[^\n]*|/\*[\s\S]*?\*/|"(?:[^"\\\r\n]|\\.)*"'
    r"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|::|[(){};,]"
)


def parse(source: str) -> Program:
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise TowerError("Source must be UTF-8 text of at most 65536 bytes.")
    tokens = []
    position = 0
    while position < len(source):
        match = TOKEN.match(source, position)
        if not match:
            raise TowerError(f"Unsupported DTL syntax at character {position}.")
        token = match.group()
        if not token.isspace() and not token.startswith(("//", "/*")):
            tokens.append(token)
        position = match.end()
    cursor = 0

    def take(expected=None):
        nonlocal cursor
        if cursor >= len(tokens):
            raise TowerError("Unexpected end of program.")
        token = tokens[cursor]
        cursor += 1
        if expected is not None and token != expected:
            raise TowerError(f"Expected {expected!r}, found {token!r}.")
        return token

    for token in ("fn", "main", "(", ")", "{"):
        take(token)
    qubits = None
    measured = False
    operations = []
    messages = []
    statements = 0
    arities = {"h": 1, "x": 1, "z": 1, "cx": 2, "measure_all": 0}
    while cursor < len(tokens) and tokens[cursor] != "}":
        statements += 1
        if statements > MAX_OPERATIONS:
            raise TowerError("At most 512 statements are allowed.")
        name = take()
        if name == "print":
            take("(")
            literal = take()
            if not literal.startswith('"'):
                raise TowerError("print requires a string literal.")
            try:
                messages.append(json.loads(literal))
            except ValueError as exc:
                raise TowerError("Invalid string escape.") from exc
            take(")")
            take(";")
            continue
        if name != "quantum":
            raise TowerError("Only print and quantum calls are supported.")
        take("::")
        gate = take()
        if gate not in arities and gate != "allocate":
            raise TowerError(f"Unsupported quantum operation: {gate}.")
        take("(")
        args = []
        count = 1 if gate == "allocate" else arities[gate]
        for index in range(count):
            if index:
                take(",")
            number = take()
            if not number.isascii() or not number.isdecimal() or len(number) > 4:
                raise TowerError("Arguments must be nonnegative integer literals.")
            args.append(int(number))
        take(")")
        take(";")
        if gate == "allocate":
            if qubits is not None or not 1 <= args[0] <= MAX_QUBITS:
                raise TowerError("Allocate 1–12 qubits exactly once before gates.")
            qubits = args[0]
            continue
        if qubits is None or measured:
            raise TowerError("Gates require allocation and must precede measurement.")
        if any(arg >= qubits for arg in args):
            raise TowerError("Qubit index is outside the allocated register.")
        if gate == "cx" and args[0] == args[1]:
            raise TowerError("Control and target must be different qubits.")
        if gate == "measure_all":
            measured = True
        else:
            operations.append((gate, tuple(args)))
    take("}")
    if cursor != len(tokens):
        raise TowerError("Unexpected content after main.")
    if qubits is None or not measured:
        raise TowerError("A program must allocate qubits and call measure_all().")
    return Program(qubits, tuple(operations), tuple(messages))


def validate_shots(shots: int):
    if type(shots) is not int or not 1 <= shots <= MAX_SHOTS:
        raise TowerError("Shots must be an integer from 1 to 8192.")


def simulate(program: Program, shots=1024, seed=None) -> dict:
    validate_shots(shots)
    state = [0j] * (1 << program.qubits)
    state[0] = 1 + 0j
    for gate, args in program.operations:
        target = 1 << args[-1]
        for index in range(len(state)):
            if index & target:
                continue
            partner = index | target
            if gate == "h":
                a, b = state[index], state[partner]
                state[index] = (a + b) / math.sqrt(2)
                state[partner] = (a - b) / math.sqrt(2)
            elif gate == "z":
                state[partner] = -state[partner]
            elif gate == "x" or (gate == "cx" and index & (1 << args[0])):
                state[index], state[partner] = state[partner], state[index]
    samples = random.Random(seed).choices(
        range(len(state)), weights=[abs(value) ** 2 for value in state], k=shots
    )
    counts = Counter(format(value, f"0{program.qubits}b") for value in samples)
    return {
        "provider": "local-simulator",
        "qubits": program.qubits,
        "shots": shots,
        "counts": dict(sorted(counts.items())),
        "messages": list(program.messages),
    }
