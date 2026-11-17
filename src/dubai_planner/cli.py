import argparse
import json
from datetime import date
from pathlib import Path

from .config import load_settings
from .providers.policy import PolicyRegistry
from .storage.repository import CatalogRepository, ImportRejected


def print_model(model):
    """Print portable JSON even when the Windows console is not UTF-8."""
    print(json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description="Validate and import the local Dubai catalog")
    parser.add_argument(
        "command",
        choices=[
            "import",
            "inspect",
            "export",
            "plan",
            "fixture-plan",
            "model-plan",
            "extract-request",
            "coverage",
        ],
    )
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument(
        "--policies", type=Path, default=Path("config/provider_policies/sources.json")
    )
    parser.add_argument("--reports", type=Path, default=Path("runtime/import-reports"))
    parser.add_argument("--base", default="area-bur-dubai")
    parser.add_argument("--accommodation")
    parser.add_argument(
        "--env-file", type=Path, help="Explicit local settings file; never executes shell code"
    )
    parser.add_argument(
        "--on-date", type=date.fromisoformat, help="Coverage travel date, YYYY-MM-DD"
    )
    args = parser.parse_args()
    try:
        settings = load_settings(env_file=args.env_file)
        if args.command == "coverage":
            from .services.coverage import coverage_report
            from .storage.repository import read_catalog

            catalog = read_catalog(args.path or settings.dataset_path)
            catalog.check_policy(PolicyRegistry.load(args.policies), "export")
            print(json.dumps(coverage_report(catalog, on_date=args.on_date), indent=2))
            return
        repository = CatalogRepository(
            args.database or settings.database_path, PolicyRegistry.load(args.policies)
        )
        if args.command == "import":
            print(
                json.dumps(
                    repository.import_file(args.path or settings.dataset_path, args.reports),
                    indent=2,
                )
            )
        elif args.command == "export":
            if not args.path:
                parser.error("export requires a destination .json or .csv")
            repository.export(args.path)
            print("Exported approved curated records")
        elif args.command == "extract-request":
            from .agents.model_specialist import extract_request
            from .services.run_service import model_session

            if not args.path:
                parser.error("extract-request requires a plain-text request file")
            catalog = repository.load()
            _, gateway = model_session(catalog, settings)
            proposed = extract_request(args.path.read_text(encoding="utf-8"), gateway)
            print_model(proposed)
        elif args.command in {"plan", "fixture-plan", "model-plan"}:
            from .domain.requests import TripRequest
            from .services.planner import plan_local

            if not args.path:
                parser.error("plan requires a structured request JSON file")
            request = TripRequest.model_validate_json(args.path.read_text(encoding="utf-8"))
            catalog = repository.load()
            catalog.check_policy(repository.registry, "export")
            if args.command in {"fixture-plan", "model-plan"}:
                from .services.run_service import run_fixture, run_model

                runner = run_model if args.command == "model-plan" else run_fixture
                result = runner(
                    request,
                    catalog,
                    repository.registry,
                    settings=settings,
                    base_id=args.base,
                    accommodation_id=args.accommodation,
                )
                print_model(result)
                return
            result = plan_local(
                request,
                catalog,
                registry=repository.registry,
                base_id=args.base,
                accommodation_id=args.accommodation,
            )
            print_model(result)
        else:
            c = repository.load()
            print(
                json.dumps(
                    {
                        "dataset_version": c.dataset_version,
                        "places": len(c.places),
                        "prices": len(c.prices),
                        "routes": len(c.routes),
                    },
                    indent=2,
                )
            )
    except (ValueError, OSError, ImportRejected) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
