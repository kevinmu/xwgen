"""File containing string utils for puzzle rendering."""


def merge_strings_with_same_num_lines(str1: str, str2: str) -> str:
    str1_lines = str1.splitlines()
    str2_lines = str2.splitlines()
    assert len(str1_lines) == len(str2_lines), \
        f"{len(str1_lines)} vs {len(str2_lines)}"

    merged_lines = [""] * len(str1_lines)
    for i in range(len(str1_lines)):
        str1_without_right_border = str1_lines[i][:-1]
        merged_lines[i] = str1_without_right_border + str2_lines[i]

    return "\n".join(merged_lines)


def remove_last_line_from_string(s: str) -> str:
    return s[:s.rfind('\n')]
