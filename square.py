"""Class representing the a single square in the crossword grid."""
from typing import Optional


class Square:
    is_black: bool
    letter: Optional[str]
    index: Optional[int]

    def __init__(
        self,
        is_black: bool = False,
        letter: str = None,
        index: int = None,
    ):
        self.is_black = is_black
        self.letter = letter
        self.index = index

    # Example of one square rendered:
    # +-------+
    # |129    |
    # |   A   |
    # +-------+
    # Example of five squares rendered next to each other,
    # with the left-most square being a black square:
    # +-------++-------++-------++-------++-------+
    # |*******||129    ||       ||       ||       |
    # |*******||   A   ||   B   ||   _   ||   A   |
    # +-------++-------++-------++-------++-------+
    def get_render_str(self):
        border_str = "+—————+"

        if self.is_black:
            # top-border
            render_str = f"{border_str}\n"
            # first row - fill w/ big black rectangles
            render_str += "|\u2588\u2588\u2588\u2588\u2588|\n"
            # second row - fill w/ big black rectangles
            render_str += "|\u2588\u2588\u2588\u2588\u2588|\n"
            # bottom-border
            render_str += border_str
            return render_str

        # top-border
        render_str = f"{border_str}\n"

        # second row with index
        render_str += "|"
        render_str += "   " if self.index is None else "{:<3d}".format(self.index)
        render_str += "  |\n"

        # third row with letter
        render_str += "|  "
        render_str += "_" if self.letter is None else self.letter
        render_str += "  |\n"

        # bottom-border
        render_str += border_str
        return render_str
