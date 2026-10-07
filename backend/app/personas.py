from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    title: str
    role: str


PERSONAS = [
    Persona("employee", "Maya Lim", "Software Engineer", "employee"),
    Persona("manager", "Daniel Ong", "Engineering Manager", "manager"),
]


def get_persona(pid: str) -> Persona:
    for p in PERSONAS:
        if p.id == pid:
            return p
    raise KeyError(pid)
