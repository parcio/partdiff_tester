"""This file contains the actual test case (see `test_partdiff_parametrized`).

The test is parametrized by `pytest_generate_tests` in `conftest.py` via its `test_id` argument.
"""

import re

import pytest

import util
from output_masks import (
    OUTPUT_MASKS,
    OUTPUT_MASKS_ALLOW_EXTRA_ITER,
    OUTPUT_MASKS_WITH_EXTRA_ITER,
)
from util import PartdiffParamsTuple, TermParam


def check_partdiff_output(
    actual_output: str,
    reference_output: str,
    mask: re.Pattern,
):
    """Check the output of partdiff using an output mask.

    This function asserts that...
    1. The actual output matches the selected output mask
    2. The reference output matches the selected output mask
    3. For all of the output mask's capture groups, that the
       captured values of actual and reference output are identical.

    Args:
        actual_output (str): The output of the tested EXECUTABLE
        reference_output (str): The output of the reference implementation
        mask (re.Pattern): The output mask.
    """
    m_actual = mask.match(actual_output)
    assert m_actual is not None, (actual_output,)
    m_expected = mask.match(reference_output)
    assert m_expected is not None, (reference_output,)
    assert len(m_expected.groups()) == len(m_actual.groups())
    for capture_expected, capture_actual in zip(m_expected.groups(), m_actual.groups()):
        assert capture_expected == capture_actual


def test_partdiff_parametrized(
    pytestconfig: pytest.Config,
    reference_output_data: dict[PartdiffParamsTuple, str],
    test_id: str,
) -> None:
    """Test if the output of a partdiff implementation matches the output of the reference implementation.

    Args:
        pytestconfig (pytest.Config): See https://docs.pytest.org/en/7.1.x/reference/reference.html#pytestconfig
        reference_output_data (dict[PartdiffParamsTuple, str]): The cached reference output data
        test_id (str): The parameters to test as a space-separated string (not a tuple because a str prints better).
    """
    partdiff_params = util.params_tuple_from_str(test_id)
    partdiff_executable = pytestconfig.getoption("executable")
    strictness = pytestconfig.getoption("strictness")
    use_valgrind = pytestconfig.getoption("valgrind")
    reference_source = pytestconfig.getoption("reference_source")
    cwd = pytestconfig.getoption("cwd")
    allow_extra_iterations = pytestconfig.getoption("allow_extra_iterations")
    timeout = pytestconfig.getoption("timeout")

    actual_output = util.get_actual_output(
        partdiff_params, partdiff_executable, use_valgrind, cwd, timeout
    )
    reference_output = util.get_reference_output(
        partdiff_params, reference_output_data, reference_source
    )
    if util.PartdiffParamsClass.from_tuple(partdiff_params).term == TermParam.ACC:
        if allow_extra_iterations != 0:
            actual_iterations = util.parse_num_iterations_from_partdiff_output(
                actual_output
            )
            reference_iterations = util.parse_num_iterations_from_partdiff_output(
                reference_output
            )
            if allow_extra_iterations != -1:
                assert (
                    actual_iterations <= reference_iterations + allow_extra_iterations
                )
            if actual_iterations != reference_iterations:
                check_partdiff_output(
                    actual_output,
                    reference_output,
                    OUTPUT_MASKS_ALLOW_EXTRA_ITER[strictness],
                )
                # Force termination condition "iterations"
                num, method, lines, func, _term, _acc_iter = partdiff_params
                partdiff_params = (
                    num,
                    method,
                    lines,
                    func,
                    "2",
                    str(actual_iterations),
                )
                reference_output = util.get_reference_output(
                    partdiff_params, reference_output_data, reference_source
                )
                check_partdiff_output(
                    actual_output,
                    reference_output,
                    OUTPUT_MASKS_WITH_EXTRA_ITER[strictness],
                )
                return
    check_partdiff_output(actual_output, reference_output, OUTPUT_MASKS[strictness])
