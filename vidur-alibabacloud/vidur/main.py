from vidur.config import SimulationConfig
from vidur.simulator import Simulator
from vidur.utils.random import set_seeds
from vidur.utils.diagnostics import add_exception_note


def main() -> None:
    config: SimulationConfig = SimulationConfig.create_from_cli_args()

    set_seeds(config.seed)

    simulator = Simulator(config)
    try:
        simulator.run()
    except Exception as execution_error:
        try:
            simulator.write_output()
        except Exception as output_error:
            add_exception_note(execution_error, f"Output also failed: {type(output_error).__name__}: {output_error}")
        raise
    else:
        simulator.write_output()


if __name__ == "__main__":
    main()
