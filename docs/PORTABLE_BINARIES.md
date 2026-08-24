# Standalone AgentMesh Gateway binaries

AgentMesh Gateway can be packaged as a single-file executable for Windows, Linux and macOS with PyInstaller. The executable embeds Python and the application dependencies, so end users do not need to install Python first.

## Windows

Download the Windows asset from the GitHub Release and run it directly. Launching the executable with no command starts the gateway on `127.0.0.1:8787`.

```powershell
.\AgentMesh-Gateway-windows-x64.exe
```

Useful commands:

```powershell
.\AgentMesh-Gateway-windows-x64.exe version
.\AgentMesh-Gateway-windows-x64.exe serve --host 127.0.0.1 --port 8787
```

## Linux

After download, make the binary executable once:

```bash
chmod +x AgentMesh-Gateway-linux-x64
./AgentMesh-Gateway-linux-x64
```

## macOS

After download, make the binary executable once:

```bash
chmod +x AgentMesh-Gateway-macos-*
./AgentMesh-Gateway-macos-*
```

The macOS binary is not Apple-notarized or Developer-ID signed. Depending on local Gatekeeper policy, macOS may require the user to explicitly allow the downloaded open-source binary before first launch.

## Integrity verification

Every generated binary is accompanied by a `.sha256` file. Verify the digest before execution when downloading release assets from an untrusted network path.

Linux/macOS example:

```bash
sha256sum -c AgentMesh-Gateway-linux-x64.sha256
```

Windows PowerShell example:

```powershell
Get-FileHash .\AgentMesh-Gateway-windows-x64.exe -Algorithm SHA256
```

Compare the resulting value with the corresponding `.sha256` release asset.

## Security and signing note

The current portable binaries are reproducible CI artifacts but are not commercially code-signed. Windows SmartScreen or macOS Gatekeeper can therefore display a warning on first launch. A future release can add Authenticode signing for Windows and Developer ID signing/notarization for macOS when suitable signing identities are available.

## Build and release behavior

`.github/workflows/portable-binaries.yml` builds and smoke-tests the executable on Windows, Linux and macOS. Pull requests validate all three platforms. Future version tags automatically attach the platform-specific binaries and their SHA-256 files to the matching GitHub Release.

The smoke test does two things on the actual packaged binary:

1. runs the `version` command;
2. starts the HTTP gateway and confirms that `/healthz` returns successfully.

This catches packaging failures that a compile-only check would miss.
