import enum
import os
import random
import re
import datetime
from typing import Any, List, Tuple, Optional

import click
import yaml

MAX_OPERATING_CEILING_M = 12497


class Config:
    xplane_directory: str
    expected_failures: float
    mtbf_hours: float
    scenario_name: Optional[str]

    def __init__(self, data: Any):
        assert isinstance(data, dict)
        self.xplane_directory = data["xplane_directory"]
        self.expected_failures = data["expected_failures"]
        self.mtbf_hours = data["mtbf_hours"]
        self.scenario_name = data.get("scenario_name")

    def description(self):
        return f"expected_failures: {self.expected_failures}; mtbf_hours: {self.mtbf_hours}"

    @property
    def challenger_dir(self):
        return os.path.expanduser(os.path.join(self.xplane_directory, "Aircraft", "X-Aviation", "CL650"))


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
            FailureState.GEAR_CYCLED
        ]

    @staticmethod
    def get_parameter_range_for_failure_state(config: Config, failure_state: "FailureState") -> \
    Optional[
        Tuple[int, int]]:
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
            case FailureState.GEAR_UP | FailureState.GEAR_DOWN | FailureState.GEAR_CYCLED:
                return None


def load_config():
    with open("failure-config.yml", "r") as file:
        config = yaml.safe_load(file)
    return Config(config)


def load_failures(config: Config):
    failures = []
    failure_conf_path = os.path.join(config.challenger_dir, "plugins", "systems", "data", "failures.conf")
    with open(failure_conf_path, "r") as file:
        lines = file.readlines()
    for line in lines:
        match = re.match(r"FAIL\t(/[\w/]+)", line)
        if match:
            failures.append(match.group(1))
    return failures


def get_random_trigger(config: Config, failure: str) -> Tuple[str, FailureState, Optional[int]]:
    trigger_choices = FailureState.triggerable_by_random_failure()
    trigger = random.choice(trigger_choices)
    param_range = FailureState.get_parameter_range_for_failure_state(config, trigger)
    if param_range is None:
        return failure, trigger, None
    return failure, trigger, random.randint(*param_range)


def get_failure_triggers(config: Config, failure_list: List[str]):
    failures_with_triggers = []
    failure_chance = config.expected_failures / len(failure_list)
    for failure in failure_list:
        if random.random() < failure_chance:
            failures_with_triggers.append(get_random_trigger(config, failure))
    return failures_with_triggers

def write_failures_to_scenario(config: Config, failure_list: List[Tuple[str, FailureState, Optional[int]]]):
    now_isoformat = datetime.datetime.now().isoformat()
    default_name = "Random failure scenario " + now_isoformat.replace(":", "-") + ".sce"
    scenario_path = os.path.join(config.challenger_dir, "plugins", "systems", "data", "stock_failures", config.scenario_name if config.scenario_name else default_name)
    with open(scenario_path, "w") as file:
        file.write(f"# Automatically generated using cl650-random-failures at {now_isoformat}\n")
        file.write(f"# Config: {config.description()}\n")
        for failure in failure_list:
            file.write("libfail" + failure[0] + "/state = " + str(failure[1].value) + "\n")
            if failure[2] is not None:
                file.write("libfail" + failure[0] + "/param = " + str(failure[2]) + "\n")
    return scenario_path

@click.command()
@click.option("--verbose", "-v", default=False, is_flag=True, help="Include additional information in stdout (like generated failures)")
def main(verbose: bool):
    config = load_config()
    failures = load_failures(config)
    assert len(failures) > 0, "No failures could be loaded from the failures.conf."
    triggers = get_failure_triggers(config, failures)
    if verbose:
        print("Failures included in generated scenario:", triggers)
    scenario_path = write_failures_to_scenario(config, triggers)
    print(f"Wrote scenario to '{scenario_path}'")


if __name__ == "__main__":
    main()
