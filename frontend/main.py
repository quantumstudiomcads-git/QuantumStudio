import sys

from PySide6.QtWidgets import QApplication

from frontend.app.project_hub import ProjectHub


def main():

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        "Quantum Studio"
    )

    app.setOrganizationName(
        "Quantum Studio"
    )

    app.setApplicationDisplayName(
        "Quantum Studio"
    )

    hub = ProjectHub()

    hub.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
