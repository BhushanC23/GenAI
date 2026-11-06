"""Interactive command-line interface for exploring Kubernetes records."""

from typing import List

from app.records import count_by, get_by_id, load_records, search


def display_record(record: dict) -> None:
    """Print the useful fields of one Kubernetes record."""
    print(f"\n{record['page_title']} [{record['id']}]")
    print(f"Category: {record['category']}")
    print(f"Definition: {record['one_line_definition']}")
    print(f"Command: {record['key_kubectl_command']}")
    print(f"Limit/default: {record['limit_or_default']}")
    print(f"Source: {record['source_url']}")


def display_menu() -> None:
    """Print the available CLI actions."""
    print("\nKubeCoach Kubernetes Records")
    print("1. Search records")
    print("2. Count records by category")
    print("3. View record by ID")
    print("0. Exit")


def main() -> None:
    """Run the interactive KubeCoach records menu."""
    records = load_records()
    print(f"Loaded {len(records)} Kubernetes records.")

    while True:
        display_menu()
        choice = input("Enter your choice: ").strip()

        if choice == "1":
            keyword = input("Enter a keyword: ")
            matches: List[dict] = search(records, keyword)
            if matches:
                for record in matches:
                    display_record(record)
            else:
                print("No matching records found.")
        elif choice == "2":
            print("\nRecords by category:")
            for category, total in sorted(count_by(records, "category").items()):
                print(f"- {category}: {total}")
        elif choice == "3":
            record_id = input("Enter a record ID: ")
            record = get_by_id(records, record_id)
            if record is None:
                print("No record found with that ID.")
            else:
                display_record(record)
        elif choice == "0":
            print("Thank you for using KubeCoach!")
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
