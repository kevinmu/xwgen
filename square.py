"""Class representing the a single square in the crossword grid."""
from dataclasses import dataclass
from typing import Optional

from entry import Entry

@dataclass
class Square:
    is_black: bool = False
    letter: Optional[str] = None
    index: Optional[int] = None
    starts_down_word: bool = False
    starts_across_word: bool = False
    across_entry_parent: Optional[Entry] = None
    down_entry_parent: Optional[Entry] = None

    # Example of one square rendered:
    # +—————+
    # |129  |
    # |  A  |
    # +—————+
    # Example of five squares rendered next to each other,
    # with the left-most square being a black square:
    # +—————++—————++—————++—————++—————+
    # |█████||129  ||     ||     ||     |
    # |█████||  A  ||  B  ||  _  ||  A  |
    # +—————++—————++—————++—————++—————+
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
