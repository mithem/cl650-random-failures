import enum
import os
import random
import re
import datetime
from typing import Any, List, Tuple, Optional, Dict

import click
import numpy as np
import yaml

MAX_OPERATING_CEILING_M = 12497


class FailureState(enum.IntEnum):
    NOT_FAILED = 0
    ACTIVE = 1
    IAS = 2
    TAS = 3
    GS = 4
    V1 = 5
    VR = 6
    V2 = 7
    VT = 8
    AMSL = 9
    AGL = 10
    WAYPOINT = 11
    EXACT_TIMEOUT = 12
    APPROX_TIMEOUT = 13
    LIFTOFF = 14
    GEAR_UP = 15
    GEAR_DOWN = 16
    GEAR_CYCLED = 17
    CTRL_F = 18

    @staticmethod
    def triggerable_by_random_failure():
        return [
            FailureState.ACTIVE,
            FailureState.IAS,
            FailureState.TAS,
            FailureState.GS,
            FailureState.V1,
            FailureState.VR,
            FailureState.V2,
            FailureState.VT,
            FailureState.AMSL,
            FailureState.AGL,
            FailureState.EXACT_TIMEOUT,
            FailureState.APPROX_TIMEOUT,
            FailureState.LIFTOFF,
            FailureState.GEAR_UP,
            FailureState.GEAR_DOWN,
            FailureState.GEAR_CYCLED,
        ]

    @staticmethod
    def get_parameter_range_for_failure_state(
        config: "Config", failure_state: "FailureState"
    ) -> Optional[Tuple[int, int]]:
        match failure_state:
            case FailureState.ACTIVE:
                return None
            case FailureState.IAS | FailureState.TAS:
                return 1, 330
            case FailureState.GS:
                return 1, 520
            case FailureState.V1 | FailureState.VR | FailureState.V2 | FailureState.VT:
                return -30, 30
            case FailureState.AMSL:
                return -100, MAX_OPERATING_CEILING_M
            case FailureState.AGL:
                return 10, 2500
            case FailureState.EXACT_TIMEOUT | FailureState.APPROX_TIMEOUT:
                return int(config.mtbf_hours / 3 * 60), int(config.mtbf_hours * 3 * 60)
            case FailureState.LIFTOFF:
                return 1, 90
            case (
                FailureState.GEAR_UP | FailureState.GEAR_DOWN | FailureState.GEAR_CYCLED
            ):
                return None


FAILURE_STATE_DISPLAY_NAMES = {
    "not-failed": FailureState.NOT_FAILED,
    "active": FailureState.ACTIVE,
    "ias": FailureState.IAS,
    "tas": FailureState.TAS,
    "gs": FailureState.GS,
    "v1": FailureState.V1,
    "vr": FailureState.VR,
    "v2": FailureState.V2,
    "vt": FailureState.VT,
    "amsl": FailureState.AMSL,
    "agl": FailureState.AGL,
    "waypoint": FailureState.WAYPOINT,
    "exact-timeout": FailureState.EXACT_TIMEOUT,
    "approx-timeout": FailureState.APPROX_TIMEOUT,
    "liftoff": FailureState.LIFTOFF,
    "gear-up": FailureState.GEAR_UP,
    "gear-down": FailureState.GEAR_DOWN,
    "gear-cycled": FailureState.GEAR_CYCLED,
    "ctrl-f": FailureState.CTRL_F,
}


class FailureOverrideEntry:
    failure: str
    state: FailureState | None
    param: int | None
    mtbf_hours: float | None
    probability_multiplier: float | None

    def __init__(
        self,
        failure: str,
        state: int | None = None,
        param: int | None = None,
        mtbf_hours: float | None = None,
        mult: float | None = None,
        **kwargs,
    ):
        self.failure = failure
        self.state = FailureState(state) if state is not None else None
        self.param = param
        self.mtbf_hours = mtbf_hours
        self.probability_multiplier = mult

    def __lt__(self, other):
        return self.failure < other.failure

    def __str__(self):
        return f"Override<failure={self.failure}, state={self.state}, param={self.param}, mtbf_hours={self.mtbf_hours}, mult={self.probability_multiplier}>"

    def __repr__(self):
        return str(self)


class StateProbabilityOverrideEntry:
    state: FailureState
    multiplier: float

    def __init__(self, state: FailureState, multiplier: float):
        self.state = state
        self.multiplier = multiplier

    def __lt__(self, other):
        return self.state.value < other.state.value

    def __str__(self):
        return f"StateOverride<state={self.state}, multiplier={self.multiplier}>"

    def __repr__(self):
        return str(self)


def _get_failure_override_entries(
    override_config: Dict[str, Any], prepend_origin: str = ""
) -> List[FailureOverrideEntry]:
    entries = []
    keywords = ["state", "param", "mtbf_hours", "mult"]
    for keyword in keywords:
        if keyword in override_config:
            entries.append(FailureOverrideEntry(prepend_origin, **override_config))
    for key, value in override_config.items():
        if key not in keywords:
            entries += _get_failure_override_entries(
                value, prepend_origin=prepend_origin + "/" + key
            )
    return entries


def _get_state_probability_override_entries(
    override_config: Dict[str, float],
) -> List[StateProbabilityOverrideEntry]:
    entries = []
    for state_name, multiplier in override_config.items():
        assert type(state_name) == str, (
            "Expected state to be string, found "
            + str(type(state_name))
            + " ("
            + str(state_name)
            + ")"
        )
        assert multiplier >= 0, (
            "Invalid multiplier "
            + str(multiplier)
            + " ("
            + str(type(multiplier))
            + ") for override for state "
            + state_name
        )
        state = FAILURE_STATE_DISPLAY_NAMES.get(state_name)
        if state is None:
            raise ValueError(
                f"State {state_name} is not valid. Expected one of: {', '.join(FAILURE_STATE_DISPLAY_NAMES.keys())}"
            )
        entry = StateProbabilityOverrideEntry(state, multiplier)
        entries.append(entry)
    return entries


class Config:
    xplane_directory: str
    expected_failures: float
    mtbf_hours: float
    scenario_name: Optional[str]
    overrides: List[FailureOverrideEntry]
    state_probability_overrides: List[StateProbabilityOverrideEntry]

    def __init__(self, data: Any):
        assert isinstance(data, dict)
        self.xplane_directory = data["xplane_directory"]
        self.expected_failures = data["expected_failures"]
        self.mtbf_hours = data["mtbf_hours"]
        self.scenario_name = data.get("scenario_name")
        self.overrides = list(
            sorted(
                _get_failure_override_entries(data.get("overrides", {})), reverse=True
            )
        )
        self.state_probability_overrides = list(
            sorted(
                _get_state_probability_override_entries(
                    data.get("state_probability_overrides", {})
                ),
                reverse=True,
            )
        )

    def description(self):
        return f"expected_failures: {self.expected_failures}; mtbf_hours: {self.mtbf_hours}; overrides: {self.overrides}; state-probability-overrides: {self.state_probability_overrides}"

    @property
    def challenger_dir(self):
        return os.path.expanduser(
            os.path.join(self.xplane_directory, "Aircraft", "X-Aviation", "CL650")
        )

    def get_override_for_failure(self, failure: str) -> FailureOverrideEntry | None:
        for override in self.overrides:
            if override.failure == failure:
                return override
            if failure.startswith(
                override.failure
            ):  # A general category (e.g. /systems/eng/left) overrides this specific failure (e.g. /systems/eng/left/rev/deploy)
                return override
        return None

    def get_state_probability_override(
        self, state: FailureState
    ) -> StateProbabilityOverrideEntry | None:
        for override in self.state_probability_overrides:
            if override.state == state:
                return override
        return None

    def get_failure_state_probability_distribution(self) -> List[float]:
        possible_states = FailureState.triggerable_by_random_failure()
        distribution = np.ones(len(possible_states))
        for i, state in enumerate(possible_states):
            override = self.get_state_probability_override(state)
            if override is not None:
                distribution[i] = override.multiplier
        return list(distribution / sum(distribution))


def load_config():
    with open("failure-config.yml", "r") as file:
        config = yaml.safe_load(file)
    return Config(config)


def load_failures(config: Config):
    failures = []
    failure_conf_path = os.path.join(
        config.challenger_dir, "plugins", "systems", "data", "failures.conf"
    )
    with open(failure_conf_path, "r") as file:
        lines = file.readlines()
    for line in lines:
        match = re.match(r"FAIL\t(/[\w/]+)", line)
        if match:
            failures.append(match.group(1))
    return failures


def get_random_trigger(
    config: Config, failure: str, override: FailureOverrideEntry | None
) -> Tuple[str, FailureState, Optional[int]]:
    if override is not None and override.state is not None:
        return failure, override.state, override.param
    trigger_choices = FailureState.triggerable_by_random_failure()
    prob_dist = config.get_failure_state_probability_distribution()
    trigger = FailureState(np.random.choice(trigger_choices, 1, p=prob_dist)[0])
    param_range = FailureState.get_parameter_range_for_failure_state(config, trigger)
    if param_range is None:
        return failure, trigger, None
    return failure, trigger, random.randint(*param_range)


def get_failure_triggers(config: Config, failure_list: List[str], verbose: bool):
    failures_with_triggers = []
    failure_chance = config.expected_failures / len(failure_list)
    for failure in failure_list:
        override: FailureOverrideEntry | None = config.get_override_for_failure(failure)
        if verbose and override is not None:
            print(f"Enabled override for failure {failure}: {override}")
        mult = (
            1
            if override is None or override.probability_multiplier is None
            else override.probability_multiplier
        )
        if random.random() < failure_chance * mult:
            failures_with_triggers.append(get_random_trigger(config, failure, override))
    return failures_with_triggers


def write_failures_to_scenario(
    config: Config, failure_list: List[Tuple[str, FailureState, Optional[int]]]
):
    now_isoformat = datetime.datetime.now().isoformat()
    default_name = "Random failure scenario " + now_isoformat.replace(":", "-") + ".sce"
    scenario_path = os.path.join(
        config.challenger_dir,
        "plugins",
        "systems",
        "data",
        "stock_failures",
        config.scenario_name if config.scenario_name else default_name,
    )
    with open(scenario_path, "w") as file:
        file.write(
            f"# Automatically generated using cl650-random-failures at {now_isoformat}\n"
        )
        file.write(f"# Config: {config.description()}\n")
        for failure in failure_list:
            file.write(
                "libfail" + failure[0] + "/state = " + str(failure[1].value) + "\n"
            )
            if failure[2] is not None:
                file.write(
                    "libfail" + failure[0] + "/param = " + str(failure[2]) + "\n"
                )
    return scenario_path


@click.command()
@click.option(
    "--verbose",
    "-v",
    default=False,
    is_flag=True,
    help="Include additional information in stdout (like generated failures)",
)
@click.option(
    "--dry",
    default=False,
    is_flag=True,
    help="Don't write any files (just show what they do)",
)
def main(verbose: bool, dry: bool):
    config = load_config()
    failures = load_failures(config)
    assert len(failures) > 0, "No failures could be loaded from the failures.conf."
    triggers = get_failure_triggers(config, failures, verbose)
    if verbose or dry:
        print("Failures included in generated scenario:", triggers)
    if not dry:
        scenario_path = write_failures_to_scenario(config, triggers)
        print(f"Wrote scenario to '{scenario_path}'")


if __name__ == "__main__":
    main()
