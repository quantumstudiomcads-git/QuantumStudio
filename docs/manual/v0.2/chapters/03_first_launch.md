# 3. First Launch

On startup Quantum Studio initializes application-data locations, configures best-effort logging, initializes local licensing state, and opens **Project Hub**. A failure to create an optional log directory does not itself prevent basic GUI startup.

The licensing bootstrap is fail-closed. A new, expired, invalid, or unavailable entitlement does not create implicit Pro or Organization access. It also does not prevent normal Project Hub use or permitted reading of existing projects and Results.

## First steps

1. Start the complete Quantum Studio standalone bundle.
2. In Project Hub, choose **New Project** to create a .qs project, or **Open Project** to open an existing one.
3. Use **Builder** to inspect or prepare the Project structure.
4. Use **Calculate** after reviewing implementation state, prerequisites, engine requirements, and entitlement.
5. Open **Analyze** after a calculation has produced a parsed Result.

> **Screenshot pending:** A native r28 window-capture surface was unavailable during B5.3; no substitute image was used.

For local entitlement information, use **Help → License Status**. Quantum Studio 0.2.0 does not document a server sign-in, billing, or organization-admin workflow because those services are not current client functionality.
