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
            python -m py_compile build_asn_mmdb.py build_geo_mmdb.py \
              dn42_registry.py iso_countries.py tools/sync_geofeed.py
          '';

          # $out/share/dn42-mmdb must be on PYTHONPATH: the entry points import
          # the shared dn42_registry and iso_countries modules, and the
          # inherited $PYTHONPATH does not include the install directory.
          installPhase = ''
            mkdir -p $out/bin $out/share/dn42-mmdb
            cp build_asn_mmdb.py build_geo_mmdb.py dn42_registry.py \
              iso_countries.py tools/sync_geofeed.py $out/share/dn42-mmdb/
            cp data/geofeed.csv $out/share/dn42-mmdb/geofeed.csv

            makeWrapper ${pkgs.python3}/bin/python $out/bin/dn42-mmdb \
              --add-flags "$out/share/dn42-mmdb/build_asn_mmdb.py" \
              --prefix PYTHONPATH : "$out/share/dn42-mmdb:$PYTHONPATH"

            # The default --geofeed is relative and would resolve against the
            # caller's cwd, silently yielding a city database with no city
            # data. Point it at the packaged snapshot; a --geofeed given on
            # the command line still wins, argparse taking the last value.
            makeWrapper ${pkgs.python3}/bin/python $out/bin/dn42-geo-mmdb \
              --add-flags "$out/share/dn42-mmdb/build_geo_mmdb.py" \
              --add-flags "--geofeed $out/share/dn42-mmdb/geofeed.csv" \
              --prefix PYTHONPATH : "$out/share/dn42-mmdb:$PYTHONPATH"

            makeWrapper ${pkgs.python3}/bin/python $out/bin/dn42-geofeed-sync \
              --add-flags "$out/share/dn42-mmdb/sync_geofeed.py" \
              --prefix PYTHONPATH : "$out/share/dn42-mmdb:$PYTHONPATH"
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
          imports = [
            (lib.mkRemovedOptionModule [ "services" "dn42-mmdb" "outputFile" ] ''
              services.dn42-mmdb.outputFile has been replaced by
              services.dn42-mmdb.stateDir, because the project now publishes
              three databases (asn, country, city) rather than one.
              Set stateDir to the directory holding them, and use
              services.dn42-mmdb.databases to select which ones to fetch.
            '')
          ];

          options.services.dn42-mmdb = {
            enable = lib.mkEnableOption "DN42 MMDB database updater service";

            stateDir = lib.mkOption {
              type = lib.types.str;
              default = "/var/lib/dn42";
              description = "Directory the MMDB database files are stored in.";
            };

            databases = lib.mkOption {
              type = lib.types.listOf (lib.types.enum [ "asn" "country" "city" ]);
              default = [ "asn" "country" "city" ];
              example = [ "asn" "country" ];
              description = ''
                Which databases to fetch. `asn` is GeoLite2-ASN compatible,
                `country` is GeoLite2-Country compatible, and `city` is
                GeoLite2-City compatible.
              '';
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
                  BASE=https://github.com/no42-org/dn42-mmdb/releases/latest/download
                  ${pkgs.coreutils}/bin/mkdir -p "${cfg.stateDir}"
                  # Download and verify everything first, install second, so a
                  # failure partway through cannot leave a half-updated set of
                  # databases behind. curl -f turns an HTTP 404 into a failure
                  # rather than an error page saved as a .mmdb.
                  for db in ${lib.concatStringsSep " " (map (d: "dn42-${d}.mmdb") cfg.databases)}; do
                    ${pkgs.curl}/bin/curl -fsSL -o "''${TMP_DIR}/''${db}" "''${BASE}/''${db}"
                    ${pkgs.curl}/bin/curl -fsSL -o "''${TMP_DIR}/''${db}.sha256" "''${BASE}/''${db}.sha256"
                    (cd "''${TMP_DIR}" && ${pkgs.coreutils}/bin/sha256sum -c "''${db}.sha256")
                  done
                  for db in ${lib.concatStringsSep " " (map (d: "dn42-${d}.mmdb") cfg.databases)}; do
                    ${pkgs.coreutils}/bin/mv "''${TMP_DIR}/''${db}" "${cfg.stateDir}/''${db}"
                    ${pkgs.coreutils}/bin/chmod 0644 "${cfg.stateDir}/''${db}"
                  done
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
