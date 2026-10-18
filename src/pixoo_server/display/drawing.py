"""Shared primitives for drawing 64-by-64 pixel-art screens."""

SIZE = 64
FONT = {
    " ": ("000", "000", "000", "000", "000"),
    "-": ("000", "000", "111", "000", "000"),
    ".": ("000", "000", "000", "000", "010"),
    ":": ("000", "010", "000", "010", "000"),
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("111", "100", "100", "100", "111"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("111", "100", "101", "101", "111"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "111"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("111", "101", "101", "101", "111"),
    "P": ("111", "101", "111", "100", "100"),
    "Q": ("111", "101", "101", "111", "001"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("111", "100", "111", "001", "111"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
}


def new_frame(color: tuple[int, int, int] = (4, 8, 14)) -> bytearray:
    """Create a display-sized RGB frame filled with one color."""
    return bytearray(color * (SIZE * SIZE))


def set_pixel(frame: bytearray, x: int, y: int, color: tuple[int, int, int]) -> None:
    """Set one RGB pixel when its coordinates are inside the display."""
    if 0 <= x < SIZE and 0 <= y < SIZE:
        offset = (y * SIZE + x) * 3
        frame[offset : offset + 3] = bytes(color)


def fill_rect(
    frame: bytearray,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    """Fill a rectangular region in a raw RGB frame."""
    for row in range(y, y + height):
        for column in range(x, x + width):
            set_pixel(frame, column, row, color)


def text_width(text: str, scale: int = 1) -> int:
    """Return the rendered width of text in the custom 3-by-5 font."""
    return max(0, len(text) * 4 * scale - scale)


def draw_text(
    frame: bytearray,
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int],
    scale: int = 1,
) -> None:
    """Draw text using the shared custom pixel font."""
    cursor = x
    for character in text.upper():
        glyph = FONT.get(character, FONT[" "])
        for row, bits in enumerate(glyph):
            for column, bit in enumerate(bits):
                if bit == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            set_pixel(
                                frame,
                                cursor + column * scale + dx,
                                y + row * scale + dy,
                                color,
                            )
        cursor += 4 * scale


def draw_centered(
    frame: bytearray,
    text: str,
    y: int,
    color: tuple[int, int, int],
    scale: int = 1,
    x_offset: int = 0,
) -> None:
    """Draw custom-font text horizontally centered on the display."""
    draw_text(
        frame,
        text,
        (SIZE - text_width(text, scale)) // 2 + x_offset,
        y,
        color,
        scale,
    )


def dim_color(color: tuple[int, int, int], level: float) -> tuple[int, int, int]:
    """Scale an RGB color for simple brightness animation."""
    return tuple(round(channel * level) for channel in color)
