import re
from typing import List, Tuple

def parse_lines(content: str) -> List[Tuple[str, str]]:
    """Retorna lista de (username, price)"""
    items = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line or not line.startswith("@"):
            continue
        if "," in line:
            user, price = line.split(",", 1)
            items.append((user.strip(), price.strip()))
        else:
            items.append((line, ""))
    return items


def has_number(username: str) -> bool:
    return bool(re.search(r"\d", username))


def char_count(username: str) -> int:
    return len(username.lstrip("@"))


def apply_filters(items: List[Tuple[str, str]], options: dict) -> List[Tuple[str, str]]:
    result = items[:]

    # tamanho 5-12
    if options.get("tamanho"):
        result = [i for i in result if 5 <= char_count(i[0]) <= 12]

    # com / sem número
    if options.get("com_numero"):
        result = [i for i in result if has_number(i[0])]
    if options.get("sem_numero"):
        result = [i for i in result if not has_number(i[0])]

    # ordenar preço
    if options.get("preco_menor"):
        def price_key(x):
            nums = re.findall(r"[\d.]+", x[1].replace(",", "."))
            return float(nums[0]) if nums else 0
        result = sorted(result, key=price_key)

    if options.get("preco_maior"):
        def price_key(x):
            nums = re.findall(r"[\d.]+", x[1].replace(",", "."))
            return float(nums[0]) if nums else 0
        result = sorted(result, key=price_key, reverse=True)

    # ordenar A-Z
    if options.get("ordenar"):
        result = sorted(result, key=lambda x: x[0].lower())

    # remover preço
    if options.get("sem_preco"):
        result = [(u, "") for u, p in result]

    return result


def to_txt(items: List[Tuple[str, str]], sem_preco: bool = False) -> str:
    lines = []
    for user, price in items:
        if sem_preco or not price:
            lines.append(user)
        else:
            lines.append(f"{user}, {price}")
    return "\n".join(lines)
