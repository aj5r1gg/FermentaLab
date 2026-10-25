# Security Policy

## Development Status

FermentaLab is experimental software.

There are no supported production releases.

The current implementation does not operate physical actuators.

## Reporting Vulnerabilities

Please do not publish exploit details before allowing a reasonable
opportunity for investigation.

For sensitive reports, use GitHub's private vulnerability reporting
feature if enabled.

If private vulnerability reporting is unavailable, open an issue
requesting a private reporting channel without disclosing sensitive
details.

## Safety-Related Issues

Report any behaviour that could result in:

- Heating and cooling being authorised simultaneously.
- Unauthorised actuator operation.
- Failure to inhibit control after a fault.
- Unsafe restart or recovery behaviour.
- Stale or invalid sensor data being accepted.
- Loss of watchdog protection.
- Unintended physical hardware operation.

Software tests do not replace independent hardware safety measures.

Do not use this development software to control mains equipment
unattended.
