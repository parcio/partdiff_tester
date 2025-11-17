"""Utility functions that are used by both `conftest.py` and `test_partdiff.py`."""

import os
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, StrEnum
from functools import cache
from pathlib import Path
from typing import Self

import output_masks

REFERENCE_IMPLEMENTATION_DIR = Path.cwd() / "reference_implementation"
REFERENCE_IMPLEMENTATION_EXEC = REFERENCE_IMPLEMENTATION_DIR / "partdiff"
REFERENCE_OUTPUT_PATH = Path.cwd() / "reference_output"
TEST_CASES_FILE_PATH = Path.cwd() / "test_cases.txt"


class ReferenceSource(StrEnum):
    """See --reference-source"""

    AUTO = "auto"
    CACHE = "cache"
    IMPL = "impl"


PartdiffParamsTuple = tuple[str, str, str, str, str, str]


class MethodParam(Enum):
    """Enum for partdiff's method parameter"""

    GAUSS_SEIDEL = 1
    JACOBI = 2


class FuncParam(Enum):
    """Enum for partdiff's func param"""

    FZERO = 1  # gotta go fast
    FPISIN = 2


class TermParam(Enum):
    """Enum for partdiff's term param"""

    ACC = 1
    ITER = 2


@dataclass
class PartdiffParamsClass:
    """Partdiff's params in a more accessible datastructure"""

    num: int
    method: MethodParam
    lines: int
    func: FuncParam
    term: TermParam
    acc_iter: int | float

    @classmethod
    def from_tuple(cls, t: PartdiffParamsTuple) -> Self:
        """Parse a PartdiffParamsClass from a PartdiffParamsTuple.

        Args:
            t (PartdiffParamsTuple): The tuple to parse.

        Returns:
            Self: The parsed PartdiffParamsClass.
        """
        num = int(t[0])
        assert 1 <= num <= 1024
        method = MethodParam(int(t[1]))
        lines = int(t[2])
        assert 0 <= lines <= 100000
        func = FuncParam(int(t[3]))
        term = TermParam(int(t[4]))
        acc_iter: int | float = -1
        if term == TermParam.ITER:
            acc_iter = int(t[5])
            assert 1 <= acc_iter <= 200000
        else:
            acc_iter = float(t[5])
            assert 1e-20 <= acc_iter <= 1e-4
        assert acc_iter != -1
        return PartdiffParamsClass(num, method, lines, func, term, acc_iter)


RE_REF_OUTPUT_FILE = re.compile(
    r"""
    ^
    partdiff
    _(1)        # num (always 1)
    _([12])     # method (1..2)
    _([0-9]+)   # lines  (0..100000)
    _([12])     # func (1..2)
    _([12])     # term (1..2)
    _([0-9e-]+) # acc/iter (1e-4..1e-20 or 1..200000)
    \.txt
    $
""",
    re.VERBOSE | re.DOTALL,
)


def iter_reference_output_data() -> Iterator[tuple[PartdiffParamsTuple, str]]:
    """Iterate over the reference output data.

    Yields:
        Iterator[tuple[PartdiffParamsTuple, str]]: An iterator over the partdiff params and the corresponding output
            of the reference implementation.
    """
    assert REFERENCE_OUTPUT_PATH.is_dir()
    for p in REFERENCE_OUTPUT_PATH.iterdir():
        m = RE_REF_OUTPUT_FILE.match(p.name)
        assert m
        partdiff_params = m.groups()
        assert len(partdiff_params) == 6
        reference_output = p.read_text()
        yield (partdiff_params, reference_output)


def iter_test_cases() -> Iterator[PartdiffParamsTuple]:
    """Iterate over the test cases.

    Yields:
        Iterator[PartdiffParamsTuple]: An iterator over the partdiff params from the test cases.
    """
    with TEST_CASES_FILE_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fields = tuple(line.split())
            assert len(fields) == 6
            yield fields


@cache
def get_test_cases() -> list[PartdiffParamsTuple]:
    """Get the test cases as a list.

    Returns:
        list[PartdiffParamsTuple]: The test cases as a list of parameter tuples.
    """
    return list(iter_test_cases())


@cache
def get_reference_output_data_map() -> dict[PartdiffParamsTuple, str]:
    """Get the reference output as a dict.

    Returns:
        dict[PartdiffParamsTuple, str]: A dict mapping parameter combinations to the corresponding output.
    """
    return dict(iter_reference_output_data())


def ensure_reference_implementation_exists() -> None:
    """Ensure that the reference implementation exists.

    If it doesn't exist, `make` is used to automatically compile it.
    """

    def is_executable():
        executable = REFERENCE_IMPLEMENTATION_EXEC
        return executable.exists() and os.access(executable, os.X_OK)

    if is_executable():
        return
    subprocess.check_output(["make", "-C", REFERENCE_IMPLEMENTATION_DIR])
    assert is_executable()


def get_reference_output(
    partdiff_params: PartdiffParamsTuple,
    reference_output_data: dict[PartdiffParamsTuple, str],
    reference_source: ReferenceSource,
) -> str:
    """Acquire the reference output.

    Args:
        partdiff_params (PartdiffParamsTuple): The parameter combination to get the output for.
        reference_output_data (dict[PartdiffParamsTuple, str]): The cached reference output.
        reference_source (ReferenceSource): The source of the reference output (cache, impl, or auto).

    Raises:
        RuntimeError: When reference_source=cache and the output for a parameter combination isn't cached.

    Returns:
        str: The reference output for the params.
    """
    # Force the number of threads to 1:
    _num, method, lines, func, term, acc_iter = partdiff_params
    partdiff_params = ("1", method, lines, func, term, acc_iter)

    def get_from_cache():
        return reference_output_data[partdiff_params]

    def get_from_impl():
        command_line = [REFERENCE_IMPLEMENTATION_EXEC] + list(partdiff_params)
        return subprocess.check_output(command_line).decode("utf-8")

    assert reference_source in ReferenceSource

    match reference_source:
        case ReferenceSource.AUTO:
            if partdiff_params in reference_output_data:
                return get_from_cache()
            return get_from_impl()
        case ReferenceSource.CACHE:
            if partdiff_params not in reference_output_data:
                raise RuntimeError(
                    'Parameter combination "{}" was not found in cache. Run with "--reference-source=auto" to fix this.'.format(
                        " ".join(partdiff_params)
                    )
                )
            return get_from_cache()
        case ReferenceSource.IMPL:
            return get_from_impl()
        case other:
            raise ValueError(f'Unexpected ReferenceSource "{other}"')


def get_actual_output(
    partdiff_params: PartdiffParamsTuple,
    partdiff_executable: list[str],
    use_valgrind: bool,
    cwd: Path | None,
    timeout: float | None,
) -> str:
    """Get the actual output for a parameter combination.

    Args:
        partdiff_params (PartdiffParamsTuple): The parameter combination.
        partdiff_executable (list[str]): The executable to run.
        use_valgrind (bool): Wether valgrind shall be used.
        cwd (Path | None): The working directory of the executable.
        timeout (float | None): The timeout in seconds, or None for no timeout.

    Returns:
        str: The output of the executable.
    """
    command_line = partdiff_executable + list(partdiff_params)
    if use_valgrind:
        command_line = ["valgrind", "--leak-check=full"] + command_line
    return subprocess.check_output(command_line, cwd=cwd, timeout=timeout).decode(
        "utf-8"
    )


def check_executable_exists(executable: list[str], cwd: Path | None) -> None:
    """Check if the executable exists and can be executed by running it.

    The executable is allowed to return a non-zero exit status.

    Args:
        executable (list[str]): The executable to check
        cwd (Path | None): The working directory of the executable.
    """
    try:
        subprocess.check_output(executable, cwd=cwd)
    except subprocess.CalledProcessError:
        pass


def params_tuple_from_str(value: str) -> PartdiffParamsTuple:
    """Parse a PartdiffParamsTuple from a space-separated str

    Args:
        value (str): The str to parse

    Returns:
        PartdiffParamsTuple: The parsed tuple
    """
    l = value.split()
    assert len(l) == 6
    num, method, lines, func, term, acc_iter = l
    return (num, method, lines, func, term, acc_iter)


def parse_num_iterations_from_partdiff_output(output: str) -> int:
    """Parse the number of iterations from partdiff's output.

    Args:
        output (str): The partdiff output to parse.

    Returns:
        int: The parsed iterations.
    """
    m = output_masks.RE_OUTPUT_MASK_FOR_ITERATIONS.match(output)
    assert m is not None
    assert len(m.groups()) == 1
    return int(m.groups()[0])
