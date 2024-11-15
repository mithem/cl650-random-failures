import enum
import os
import random
import re
from typing import Any, List, Tuple, Optional

import yaml

MAX_OPERATING_CEILING_FT = 41000


class Config:
    xplane_directory: str
    expected_failures: float
    mtbf_hours: float

    def __init__(self, data: Any):
        assert isinstance(data, dict)
        self.xplane_directory = data["xplane_directory"]
        self.expected_failures = data["expected_failures"]
        self.mtbf_hours = data["mtbf_hours"]


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
                return -100, MAX_OPERATING_CEILING_FT
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
    failure_conf_path = os.path.expanduser(os.path.join(config.xplane_directory, "Aircraft", "X-Aviation", "CL650",
                                     "plugins", "systems", "data", "failures.conf"))
    with open(failure_conf_path, "r") as file:
        lines = file.readlines()
    for line in lines:
        match = re.match(r"FAIL\t(/[\w/]+)", line)
        if match:
            failures.append(match.group(1))
    return failures


def get_random_trigger(config: Config, failure: str):
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


def main():
    config = load_config()
    failures = load_failures(config)
    triggers = get_failure_triggers(config, failures)
    print(triggers)


if __name__ == "__main__":
    main()
