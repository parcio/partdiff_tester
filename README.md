# partdiff_tester

This repository contains a testing script for `partdiff` based on `pytest`.

## Dependencies

- `uv`\*
- `valgrind` (optional)
- `make` (optional)
- a C compiler (optional)

\*: When you don't want to use `uv`, you can install the Python dependencies manually:
- Python
- `pytest`
- `pytest-xdist` (optional)

## How it works

`partdiff_tester` is based on `pytest` which is a testing framework for Python.
`pytest` automatically picks up the tests contained in `test_partdiff.py`[^1] and uses `conftest.py` for configuration.
The test cases are loaded from `test_cases.txt`; `pytest` generates the test cases automatically. The selection of test cases can be modified via the arguments `--num-threads`, `--filter`, `--shuffle`, and `--max-num-tests`.

[^1]: See https://docs.python.org/3/library/unittest.html#unittest-test-discovery

The output of a partdiff executable is simply compared to the output of the known good reference implementation.
The strictness of this check is configurable via the `--strictness` argument, e.g. with `--strictness=0`, only the matrix is compared, and with `--strictness=4`, the output has to match completely (except for the actual values of runtime and memory consumption).
If desired, a `valgrind` check can also be performed (see `--valgrind`).

The directory `reference_output` contains a collection of cached reference outputs.
If a test case is supposed to test a parameter configuration of which the output isn't cached, the reference implementation can also be used instead (see `--reference-source`).
The content of `reference_output` and `test_cases.txt` is generated with the `make_reference_output.sh` script.

## Usage

Example usage:

```shell
$ uv run pytest --executable='/path/to/partdiff'
```

Of course, you can also install `pytest` and execute it directly.

We can use the [`pytest-xdist` plugin](https://pypi.org/project/pytest-xdist/) to execute the test cases in parallel. It is recommended to do so for all serial implementations, because the parallelism greatly accelerates the tests. To do this, we simply pass the `-n auto` arguments to `pytest` (special care must be taken if you want to use `--shuffle`!)

The following performs a soundness check by essentially testing the reference implementation against itself. 

```shell
$ uv run pytest -n auto --verbose \
  --executable='reference_implementation/partdiff' \
  --strictness=4 \
  --valgrind \
  --shuffle=$RANDOM
```

If this fails, the tests are not correct or do not match the reference implementation.

The test contains some custom options:

```shell
$ uv run pytest --help | awk '/^Custom options for test_partdiff/{y=1}/^\[pytest\]/{y=0}y'
Custom options for test_partdiff:
  --executable=EXECUTABLE
                        Path to partdiff executable.
  --strictness={0,1,2,3,4}
                        Strictness of the check (default: 1)
  --valgrind            Use valgrind to execute the given executable.
  --max-num-tests=n     Only perform n tests (default: 0 == unlimited).
  --reference-source={auto,cache,impl}
                        Select the source of the reference output (cache
                        (default) == use only cached output from disk; impl ==
                        always execute reference implementation; auto == try
                        cache and fall back to impl).
  --num-threads=n       Run the tests with n threads (default: 1). Comma-
                        separated lists and number ranges are supported (e.g.
                        "1-3,5-6").
  --filter=FILTER       Filter the test configs with regex. You can pass a
                        single regex with "r:" (e.g. 'r:\w+ 1 \w+ \w+ \w+ \w+'),
                        a JSON-object with "o:" (e.g. 'o:{"method": "1"}'), or a
                        JSON-sequence with "s:" (e.g. 's:["\\w+", "1", "\\w+",
                        "\\w+", "\\w+", "\\w+"]').
  --cwd=CWD             Set the working directory when launching EXECUTABLE
                        (default: $PWD).
  --shuffle=[SEED]      Shuffle the test cases.
  --allow-extra-iterations=n
                        For term=acc, allow more iterations than the (serial)
                        reference implementation would do (0 == disallow; n ==
                        allow n more; -1 == unlimited)
  --timeout=n           Stop EXECUTABLE after n seconds (can be float).
```

The custom options are explained below.

> [!NOTE]
> Some parameters modify the set of test cases. They are applied in this order:
> 1. `--num-threads`
> 2. `--filter`
> 3. `--shuffle`
> 4. `--max-num-tests`

### `executable`

Path to the partdiff executable.

Use `--executable=/path/to/partdiff` (not `--executable /path/to/partdiff` because pytest's argparser is a bit dumb).

You can pass a space-separated list to do something like this:

```shell
$ uv run pytest --executable='mpirun -np 2 /path/to/partdiff'
```

Quoting is supported, so this works:

```shell
$ uv run pytest --executable='"/path/to/your weird/partdiff"'
```

### `strictness`

Use `--strictness` to control which parts of the output are checked:

| Strictness level | What is checked? |
|-|-|
| 0 | Only the matrix |
| 1 | Matrix and residuum (right-hand-side) |
| 2 | Matrix, right-hand-side of {interlines, number of iterations, residuum} |
| 3 | Matrix, right-hand-side of {calculation method, interlines, pertubation function, number of iterations, residuum}, left-hand-side of {calculation time, memory usage, calculation method, interlines, pertubation function, number of iterations, residuum} |
| 4 | Full char-by-char diff (except for calculation time and memory usage) |

## `valgrind`

Start the executable with `valgrind --leak-check=full`.

This takes very long!

### `max-num-tests`

Limit the total number of tests to `n` (default: 0).

If `n=0`, all tests are performed.

### `reference_source`

Control which data source is used to obtain the reference output:

- `cache` (default) ==> Load from `reference_output` only
- `impl` ==> Start partdiff in `reference_implementation` only
- `auto` ==> Try to read from `reference_output` and fall back to reference impl, if data is not available

### `num-threads`

Run the tests with `n` threads (default: 1).

You can pass a comma-separated list that may also contain ranges, so this works: `1-4,8-16`.

The tests are repeated for all selected number of threads.

Only the partdiff implementation given by `--executable=EXECUTABLE` is affected by this setting; for the reference output, a thread number of 1 is used.
So for example, when `--num-threads=8` is used, the console might show a test like
```
test_partdiff.py::test_partdiff_parametrized[8 1 0 2 2 1000]
```
Here, `EXECUTABLE` will be started with the parameters `8 1 0 2 2 1000`, but the reference output will be obtained by reading from `reference_output/partdiff_1_1_0_2_2_1000.txt` or by running `reference_implementation/partdiff 1 1 0 2 2 1000` (depending on the value of `--reference-source`).

> [!TIP]
> If you want to test a partdiff that was parallelized with MPI, you can do that by modifying `--executable`.
> This should work:
> ```shell
> for nprocs in {1..8} ; do
>   uv run pytest --executable="$(printf 'mpirun -np %d /path/to/partdiff' "$nprocs")"
> done
>  ```

### `filter`

Filter the tests with regex.

You can pass multiple different kinds of values to this argument:

- Prepend `r:` to pass a single regex that has to match the space-separated list of parameters that are passed to partdiff.
  E.g. when passing `--filter='r:\w+ 1 \w+ \w+ \w+ \w+'`, only tests with Gauss-Seidel will be selected (since the second argument has to be "1").
- Prepend `s:` to pass a JSON-sequence of regexes that will be applied to each of the parameters that are passed to partdiff.
  E.g. pass `'--filter=s:["\\w+", "1", "\\w+", "\\w+", "\\w+", "\\w+"]'` to filter for Gauss-Seidel.
  The sequence has to be a 6-tuple (since partdiff expects 6 parameters) and all sequence members have to be a valid regex as string.
- Prepend `o:` to pass a JSON-object, where the allowed keys are `("num", "method", "lines", "func", "term", "prec/iter")` and the values will be valid regexes as str.
  E.g. pass `--filter='o:{"method": "1"}'` to filter for Gauss-Seidel.

This setting is applied after `num-threads`, so you can filter `num` too.

`--filter` can be passed multiple times.

### `cwd`

Set the working directory of `EXECUTABLE`.

### `shuffle`

Shuffle the test cases. Might be handy if you want to quickly test 10 random cases or so (`--shuffle --max-num-tests=10`).

You can also pass an explicit seed with `--shuffle=n` for when you want deterministic yet random-looking results.

> [!IMPORTANT]
> If you want to use `pytest-xdist`'s parallelism with `--shuffle`, you **must** pass the seed. If you still want a random seed, you can use this trick:
> ```shell
> $ uv run pytest -n auto --executable='/path/to/partdiff' --shuffle=$RANDOM
> ```

### `allow-extra-iterations`

When choosing termination by precision, an implementation of partdiff that has been parallelized with MPI might perform more iterations than the serial reference implementation. In general, this behaviour is allowed, as long as the output (matrix and residuum) is identical to the reference implementation's output when it performs the same number of iterations.

Example:

When started with the parameters `1 1 0 2 1 1e-4`, the reference implementation terminates after 48 iterations with a residuum of `9.154544e-05`.

With the same parameters, an `mpi-partdiff` might terminate after 50 iterations with a residuum of `6.669574e-05` (which is better).

When starting the reference implementation with the parameters `1 1 0 2 2 50`, it also terminates after 50 iterations with a resiuum of `6.669574e-05`.

Therefore, the `mpi-partdiff` can be considered correct.

Allowed values for this parameter are:
- `--allow-extra-iterations=0`: Do not allow extra iterations (default)
- `--allow-extra-iterations=<n>`: Allow `n` iterations more than the serial implementation does
- `--allow-extra-iterations=-1`: Allow an unlimited number of extra iterations

> [!IMPORTANT]
> Since `partdiff_tester` probably needs to execute the reference implementation in the described scenario, it is best to always pass `--reference-source=auto` alongside this parameter. Otherwise, the tests will likely fail.

### `timeout`

A timeout in seconds for `EXECUTABLE`. Zero means no timeout.
