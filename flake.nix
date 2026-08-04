# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: MIT

{
  description = "Build a GeoLite2-ASN-compatible MaxMind MMDB database from the DN42 registry";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonPackages = pkgs.python3Packages;

        mmdb-writer = pythonPackages.buildPythonPackage rec {
          pname = "mmdb_writer";
          version = "0.2.7";
          format = "pyproject";

          src = pythonPackages.fetchPypi {
            inherit pname version;
            hash = "sha256-sBJ5eytj1rjf4hz6k5E5XntbkuFmglvTrUck9aZwIVo=";
          };

          nativeBuildInputs = [
            pythonPackages.flit-core
          ];

          propagatedBuildInputs = [
            pythonPackages.netaddr
          ];

          doCheck = false;
        };

        dn42-mmdb-pkg = pythonPackages.buildPythonApplication {
          pname = "dn42-mmdb";
          version = "0.1.0";
          src = ./.;

          format = "other";

          propagatedBuildInputs = [
            mmdb-writer
            pythonPackages.netaddr
          ];

          nativeBuildInputs = [ pkgs.makeWrapper ];

          buildPhase = ''
            python -m py_compile build_asn_mmdb.py
          '';

          installPhase = ''
            mkdir -p $out/bin $out/share/dn42-mmdb
            cp build_asn_mmdb.py $out/share/dn42-mmdb/
            makeWrapper ${pkgs.python3}/bin/python $out/bin/dn42-mmdb \
              --add-flags "$out/share/dn42-mmdb/build_asn_mmdb.py" \
              --prefix PYTHONPATH : "$PYTHONPATH"
          '';
        };
      in
      {
        packages.default = dn42-mmdb-pkg;
        packages.dn42-mmdb = dn42-mmdb-pkg;

        apps.default = {
          type = "app";
          program = "${dn42-mmdb-pkg}/bin/dn42-mmdb";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pkgs.python3
            mmdb-writer
            pythonPackages.netaddr
            pkgs.actionlint
            pkgs.git
            pkgs.gnumake
          ];
        };
      }) // {
      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.dn42-mmdb;
        in
        {
          options.services.dn42-mmdb = {
            enable = lib.mkEnableOption "DN42 MMDB database updater service";

            outputFile = lib.mkOption {
              type = lib.types.str;
              default = "/var/lib/dn42/dn42-asn.mmdb";
              description = "Path where the dn42-asn.mmdb database file will be stored.";
            };

            autoUpdate = {
              enable = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Whether to enable weekly automatic updates of the database.";
              };

              calendar = lib.mkOption {
                type = lib.types.str;
                default = "Mon *-*-* 04:00:00";
                description = "Systemd OnCalendar expression for automatic updates.";
              };
            };
          };

          config = lib.mkIf cfg.enable {
            systemd.services.dn42-mmdb-update = {
              description = "Fetch latest DN42 MaxMind MMDB database";
              after = [ "network-online.target" ];
              wants = [ "network-online.target" ];
              serviceConfig = {
                Type = "oneshot";
                StateDirectory = "dn42";
                ExecStart = pkgs.writeShellScript "dn42-mmdb-update" ''
                  set -euo pipefail
                  TMP_DIR=$(mktemp -d)
                  trap "rm -rf ''${TMP_DIR}" EXIT
                  ${pkgs.curl}/bin/curl -sSL -o "''${TMP_DIR}/dn42-asn.mmdb" https://github.com/no42-org/dn42-mmdb/releases/latest/download/dn42-asn.mmdb
                  ${pkgs.curl}/bin/curl -sSL -o "''${TMP_DIR}/dn42-asn.mmdb.sha256" https://github.com/no42-org/dn42-mmdb/releases/latest/download/dn42-asn.mmdb.sha256
                  (cd "''${TMP_DIR}" && ${pkgs.coreutils}/bin/sha256sum -c dn42-asn.mmdb.sha256)
                  ${pkgs.coreutils}/bin/mkdir -p "$(${pkgs.coreutils}/bin/dirname "${cfg.outputFile}")"
                  ${pkgs.coreutils}/bin/mv "''${TMP_DIR}/dn42-asn.mmdb" "${cfg.outputFile}"
                  ${pkgs.coreutils}/bin/chmod 0644 "${cfg.outputFile}"
                '';
              };
            };

            systemd.timers.dn42-mmdb-update = lib.mkIf cfg.autoUpdate.enable {
              description = "Weekly fetch of latest DN42 MaxMind MMDB database";
              wantedBy = [ "timers.target" ];
              timerConfig = {
                OnCalendar = cfg.autoUpdate.calendar;
                RandomizedDelaySec = "1800";
                Persistent = true;
              };
            };
          };
        };
    };
}
