"""This file is automatically picked up by `pytest` to configure the tests.

Here, we use it for the following things:

1. Declaring additional test arguments with `pytest_addoption`:
   https://docs.pytest.org/en/7.1.x/reference/reference.html#pytest.hookspec.pytest_addoption
   https://docs.pytest.org/en/stable/example/simple.html#pass-different-values-to-a-test-function-depending-on-command-line-options

2. Parametrizing tests with `pytest_generate_tests`:
   https://docs.pytest.org/en/7.1.x/reference/reference.html#pytest.hookspec.pytest_generate_tests
   https://docs.pytest.org/en/stable/how-to/parametrize.html
   https://docs.pytest.org/en/stable/example/parametrize.html

3. Supplying fixtures to the test file:
   https://docs.pytest.org/en/stable/reference/fixtures.html#conftest-py-sharing-fixtures-across-multiple-files
"""

import itertools
import json
import random
import re
import shlex
import shutil
from enum import Enum
from pathlib import Path

import pytest

import output_masks
import util
from util import PartdiffParamsTuple, ReferenceSource


def shlex_list_str(value: str) -> list[str]:
    """Parse a space-separated (and possibly quoted) string into a list of strings using shlex.

    Args:
        value (str): The string to parse.

    Returns:
        list[str]: The parsed list.
    """
    return shlex.split(value)


def reference_source_param(value: str) -> ReferenceSource:
    """Parse a ReferenceSource from str.

    Args:
        value (str): The str to parse.

    Returns:
        ReferenceSource: The parsed ReferenceSource.
    """
    return ReferenceSource(value)


REGEX_NUM_LIST = re.compile(r"^(?:\d+(?:-\d+)?)(?:,\d+(?:-\d+)?)*$")


def num_list(value: str) -> list[int]:
    """Parse a comma-separated list of numbers (possibly containing ranges) from a str.

    Some example for valid values:
    - "1,2,3"
    - "1-3"
    - "1-3,5-8"

    The list must be sorted and must not contain duplicates.

    Args:
        value (str): The str to parse.

    Returns:
        list[int]: The parsed list.
    """

    def is_sorted(l) -> bool:
        return all(l[i] <= l[i + 1] for i in range(len(l) - 1))

    def is_unique(l) -> bool:
        return len(set(l)) == len(l)

    if not REGEX_NUM_LIST.match(value):
        raise ValueError(f'Unable to parse number list "{value}"')
    result = []
    l = value.split(",")
    for x in l:
        if "-" in x:
            start, end = [int(s) for s in x.split("-")]
            result += list(range(start, end + 1))
        else:
            result.append(int(x))
    if not is_sorted(result) or not is_unique(result):
        raise ValueError(
            f'Number range "{value}" is not sorted or elements are not unique'
        )

    return result


def partdiff_params_filter_regex(value: str) -> re.Pattern:
    """Parse a partdiff params filter from a str.

    The following variants are allowed:
    - "r:<regex>", where regex has to match the space-separated list of partdiff params
    - "s:<sequence>", where sequence is a JSON sequence of regexes matching the individual partdiff params
    - "o:<object>", where object is a JSON object matching the partdiff params by their name

    Args:
        value (str): The str to parse.

    Returns:
        re.Pattern: The parsed regex.
    """

    def parse_json_sequence(value: str) -> re.Pattern:
        try:
            j = json.loads(value)
        except json.decoder.JSONDecodeError as e:
            raise ValueError("Ivalid JSON.") from e
        if not isinstance(j, list):
            raise ValueError("Not a sequence.")
        if len(j) != 6:
            raise ValueError("Incorrect length.")
        for s in j:
            if not isinstance(s, str):
                raise ValueError("Sequence member not a str.")
        try:
            return re.compile(" ".join(j))
        except re.PatternError as e:
            raise ValueError("Incorrect regex in sequence.") from e

    def parse_json_object(value: str) -> re.Pattern:
        try:
            j = json.loads(value)
        except json.decoder.JSONDecodeError as e:
            raise ValueError("Ivalid JSON.") from e
        if not isinstance(j, dict):
            raise ValueError("Not an object.")
        if len(j.keys()) != len(set(j.keys())):
            raise ValueError("Keys not unique.")
        for k, v in j.items():
            if not isinstance(k, str):
                raise ValueError("Object key not a str.")
            if not isinstance(v, str):
                raise ValueError("Object value not a str.")
        allowed_params = ("num", "method", "lines", "func", "term", "acc/iter")
        if not set(j.keys()).issubset(allowed_params):
            raise ValueError("Invalid params.")
        try:
            return re.compile(" ".join(j.get(p, r"\w+") for p in allowed_params))
        except re.PatternError as e:
            raise ValueError("Incorrect regex in object.") from e

    def parse_regex_str(value: str) -> re.Pattern:
        try:
            return re.compile(value)
        except re.PatternError as e:
            raise ValueError("Incorrect regex.") from e

    filter_variant = value[:2]
    value = value[2:]
    match filter_variant:
        case "r:":
            return parse_regex_str(value)
        case "o:":
            return parse_json_object(value)
        case "s:":
            return parse_json_sequence(value)
    raise ValueError(f'The filter "{value}" could not be parsed.')


def dir_path(value: str) -> Path:
    """Parse a directory Path from a str.

    Args:
        value (str): The str to parse.

    Raises:
        ValueError: When the given value does not exist or is not a directory.

    Returns:
        Path: The parsed path.
    """
    p = Path(value)
    if not p.exists():
        raise ValueError(f'Path "{value}" does not exist.')
    if not p.is_dir():
        raise ValueError(f'Path "{value}" is not a directory.')
    return p


def extra_iterations(value: str) -> int:
    """Parse a value for the --allow-extra-iterations parameter.

    Args:
        value (str): The value to parse.

    Raises:
        ValueError: When value doesn't contain an int between -1 and +inf

    Returns:
        int: The parsed int.
    """
    result = int(value)
    if result < -1:
        raise ValueError(
            f'Illegal value for extra-iterations "{value}", must be -1, 0, or positive.'
        )
    return result


class ShuffleType(Enum):
    """Different values for the --shuffle parameter"""

    NO_SHUFFLE = 1  # --shuffle not passed
    SHUFFLE_AUTO_SEED = 2  # --shuffle passed
    SHUFFLE_EXPL_SEED = 3  # --shuffle=n passed


def shuffle_type(value: str) -> tuple[ShuffleType, int | None]:
    """Parse a shuffle type.

    This method only gets called when --shuffle=n is passed.
    Therefore it must always return (SHUFFLE_EXPL_SEED, n).

    Args:
        value (str): The str to parse.

    Returns:
        tuple[ShuffleType, int | None]: parsed shuffle type.
    """
    return (ShuffleType.SHUFFLE_EXPL_SEED, int(value))


def timeout(value: str) -> float | None:
    """Parse a timeout value from a str.

    Args:
        value (str): The value to parse.

    Raises:
        ValueError: When the value cannot be parsed or is not a non-negative
          float.

    Returns:
        float | None: The parsed timeout, or None if 0 was passed.
    """
    parsed_value = float(value)
    if parsed_value < 0:
        raise ValueError("Timeout must be positive.")
    if parsed_value == 0.0:
        return None
    return parsed_value


def pytest_addoption(parser: pytest.Parser) -> None:
    """
    See https://docs.pytest.org/en/7.1.x/reference/reference.html#pytest.hookspec.pytest_addoption
    """
    custom_options = parser.getgroup("Custom options for test_partdiff")
    custom_options.addoption(
        "--executable",
        help="Path to partdiff executable.",
        required=True,
        type=shlex_list_str,
    )
    custom_options.addoption(
        "--strictness",
        help="Strictness of the check (default: 1)",
        type=int,
        default=1,
        choices=range(output_masks.NUM_OUTPUT_MASKS),
    )
    custom_options.addoption(
        "--valgrind",
        help="Use valgrind to execute the given executable.",
        action="store_true",
    )
    custom_options.addoption(
        "--max-num-tests",
        metavar="n",
        help="Only perform n tests (default: 0 == unlimited).",
        type=int,
        default=0,
    )
    custom_options.addoption(
        "--reference-source",
        help=(
            "Select the source of the reference output "
            "(cache (default) == use only cached output from disk; "
            "impl == always execute reference implementation; "
            "auto == try cache and fall back to impl)."
        ),
        type=reference_source_param,
        default=ReferenceSource.CACHE,
        choices=ReferenceSource,
    )
    custom_options.addoption(
        "--num-threads",
        metavar="n",
        help=(
            "Run the tests with n threads (default: 1). "
            'Comma-separated lists and number ranges are supported (e.g. "1-3,5-6").'
        ),
        type=num_list,
        default=[1],
    )
    custom_options.addoption(
        "--filter",
        help=(
            re.sub(
                r"\s+",
                " ",
                r"""
            Filter the test configs with regex.
            You can pass a single regex with "r:"
            (e.g. 'r:\w+ 1 \w+ \w+ \w+ \w+'),
            a JSON-object with "o:"
            (e.g. 'o:{"method": "1"}'),
            or a JSON-sequence with "s:"
            (e.g. 's:["\\w+", "1", "\\w+", "\\w+", "\\w+", "\\w+"]').
            """,
            ).strip()
        ),
        action="append",
        type=partdiff_params_filter_regex,
        default=[],
    )
    custom_options.addoption(
        "--cwd",
        help=("Set the working directory when launching EXECUTABLE (default: $PWD)."),
        type=dir_path,
        default=None,
    )
    custom_options.addoption(
        "--shuffle",
        help="Shuffle the test cases.",
        nargs="?",
        metavar="SEED",
        type=shuffle_type,
        const=(ShuffleType.SHUFFLE_AUTO_SEED, None),
        default=(ShuffleType.NO_SHUFFLE, None),
    )
    custom_options.addoption(
        "--allow-extra-iterations",
        help="For term=acc, allow more iterations than the (serial) reference implementation would do (0 == disallow; n == allow n more; -1 == unlimited)",
        metavar="n",
        type=extra_iterations,
        default=0,
    )
    custom_options.addoption(
        "--timeout",
        help="Stop EXECUTABLE after n seconds (can be float). Zero means no timeout.",
        metavar="n",
        type=timeout,
        default=None,
    )


@pytest.fixture
def reference_output_data() -> dict[PartdiffParamsTuple, str]:
    """
    See util.get_reference_output_data_map()
    """
    return util.get_reference_output_data_map()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """
    See https://docs.pytest.org/en/7.1.x/reference/reference.html#pytest.hookspec.pytest_generate_tests
    """
    if "test_id" in metafunc.fixturenames:
        max_num_tests = metafunc.config.getoption("max_num_tests")
        num_threads_list = metafunc.config.getoption("num_threads")
        filter_regexes = metafunc.config.getoption("filter")
        do_shuffle = metafunc.config.getoption("shuffle")
        test_cases = util.get_test_cases()

        # 1. Apply the selected number of threads:
        test_cases = [
            (str(num), method, lines, func, term, acc_iter)
            for (
                num,
                (_old_num, method, lines, func, term, acc_iter),
            ) in itertools.product(num_threads_list, test_cases)
        ]

        # Interlude: Soundness check of the partdiff parameters by trying to parse each tuple.
        for test_case in test_cases:
            # This throws an exception if we have incorrect test cases:
            _ = util.PartdiffParamsClass.from_tuple(test_case)

        # 2. Apply the filter regexes (if desired):
        test_cases = [
            test_case
            for test_case in test_cases
            if all(regex.match(" ".join(test_case)) for regex in filter_regexes)
        ]

        # 3. Shuffle the tests (if desired):
        if do_shuffle[0] in (
            ShuffleType.SHUFFLE_AUTO_SEED,
            ShuffleType.SHUFFLE_EXPL_SEED,
        ):
            random.shuffle(test_cases)

        # 4. Apply max. number of tests (if desired):
        if max_num_tests:
            test_cases = test_cases[:max_num_tests]

        test_ids = [" ".join(test_case) for test_case in test_cases]
        metafunc.parametrize("test_id", test_ids)


def pytest_configure(config: pytest.Config) -> None:
    """
    See https://docs.pytest.org/en/7.1.x/reference/reference.html#pytest.hookspec.pytest_configure
    """
    if config.getoption("executable") is None:
        return

    match config.getoption("shuffle"):
        case (ShuffleType.SHUFFLE_EXPL_SEED, seed):
            random.seed(seed)
        case (_, _):
            pass

    if config.getoption("reference_source") in (
        ReferenceSource.AUTO,
        ReferenceSource.IMPL,
    ):
        util.ensure_reference_implementation_exists()

    util.check_executable_exists(
        config.getoption("executable"), config.getoption("cwd")
    )

    if config.getoption("valgrind"):
        if shutil.which("valgrind") is None:
            raise RuntimeError("Passed --valgrind, but valgrind could not be found.")
