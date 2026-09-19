{
  description = "Terraria mod set with recoverable large-file parts";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {
    self,
    nixpkgs,
  }: let
    lib = nixpkgs.lib;
    systems = [
      "x86_64-linux"
      "aarch64-linux"
      "x86_64-darwin"
      "aarch64-darwin"
    ];
    forAllSystems = lib.genAttrs systems;
    rootEntries = builtins.readDir ./.;
    modsets =
      builtins.filter
      (name:
        rootEntries.${name}
        == "directory"
        && (builtins.pathExists (./. + "/${name}/plugins")
          || builtins.pathExists (./. + "/${name}/config")))
      (builtins.attrNames rootEntries);
  in {
    packages = forAllSystems (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
        tool = name: script:
          pkgs.writeShellApplication {
            inherit name;
            runtimeInputs = [pkgs.python3];
            text = ''
              exec python3 ${script} "$@"
            '';
          };
        recoverArgs = modsetsToCopy:
          builtins.map (modset: "--modset ${lib.escapeShellArg modset}") modsetsToCopy;
        copyModset = modset: ''
          cp -R -- ${lib.escapeShellArg modset} "$out"/
        '';
        modsetPackage = modsetsToCopy: pname:
          pkgs.stdenvNoCC.mkDerivation {
            inherit pname;
            version = "0";
            src = self;

            nativeBuildInputs = [pkgs.python3];

            dontConfigure = true;
            dontBuild = true;

            installPhase = ''
              runHook preInstall
              mkdir -p "$out"
              ${lib.concatMapStrings copyModset modsetsToCopy}
              chmod -R u+w "$out"
              python3 ${./scripts/recover.py} "$out" ${lib.concatStringsSep " " (recoverArgs modsetsToCopy)}
              runHook postInstall
            '';
          };
        modsetPackages = lib.genAttrs modsets (modset: modsetPackage [modset] "terraria-modset-${modset}");
      in
        rec {
          compress = tool "compress" ./scripts/compress.py;
          recover = tool "recover" ./scripts/recover.py;

          tools = pkgs.symlinkJoin {
            name = "terraria-modset-tools";
            paths = [
              compress
              recover
            ];
          };

          all = modsetPackage modsets "terraria-modsets";
          default = all;
        }
        // modsetPackages
    );

    apps = forAllSystems (system: {
      compress = {
        type = "app";
        program = "${self.packages.${system}.compress}/bin/compress";
      };
      recover = {
        type = "app";
        program = "${self.packages.${system}.recover}/bin/recover";
      };
    });

    devShells = forAllSystems (system: {
      default = nixpkgs.legacyPackages.${system}.mkShell {
        packages = [nixpkgs.legacyPackages.${system}.python3];
      };
    });
  };
}
