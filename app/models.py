from dataclasses import dataclass


@dataclass
class Student:
    id: int
    name: str
    surname: str
    lastname: str
    course: int
    group_name: str