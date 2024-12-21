import builtins
import contextlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from subprocess import CompletedProcess

from rich import print

DEFAULT_PACKER_SETTINGS: dict[str, str] = {
    "maker_code": "01",
    "game_code": "ENAE",
    "game_title": "NDSPACKER",
}

# == Utility Functions == #


def get_tool_prefix() -> str:
    if shutil.which("arm-none-eabi-readelf"):
        return "arm-none-eabi-"

    if shutil.which("llvm-readelf"):
        return "llvm-"

    raise FileNotFoundError("Can't find a valid readelf tool")


TOOL_PREFIX = get_tool_prefix()


def run_with_echo(command: list[str]) -> CompletedProcess[str]:
    """
    Runs a command with an echo of the actual command.
    """

    print(f"[cyan]running command:[/cyan] [pink]{command[0]}[/pink] {' '.join(command[1:])}")
    return subprocess.run(command, stdout=subprocess.PIPE, check=True, encoding="utf-8")


# == Processing functions == #


def get_elf_headers(elf_path: Path) -> dict[str, str]:
    """
    Gets the ELF headers of the specified file.
    """

    result = run_with_echo([TOOL_PREFIX + "readelf", "-h", str(elf_path)])

    # readelf output always starts with ELF Headers:
    lines = result.stdout.splitlines()[1:]
    headers: dict[str, str] = {}

    for line in lines:
        key, value = line.split(":", 1)
        key = key.lower().strip().replace(" ", "_")
        # undo the fancy aligned output
        value = value.strip()
        headers[key] = value

    return headers


def read_arm7_from_rom(raw_rom: bytes) -> tuple[int, bytes]:
    """
    Reads the ARM7 blob from a ROM file. Returns (entrypoint, blob).
    """

    entrypoint = int.from_bytes(raw_rom[0x34 : 0x34 + 4], byteorder="little")
    rom_offset = int.from_bytes(raw_rom[0x30 : 0x30 + 4], byteorder="little")
    rom_size = int.from_bytes(raw_rom[0x3C : 0x3C + 4], byteorder="little")

    return (entrypoint, raw_rom[rom_offset : rom_offset + rom_size])


def read_from_elf(elf_path: Path) -> bytes:
    """
    Reads the raw ROM file from an ELF file, using objdump.
    """

    with tempfile.TemporaryDirectory() as tdir:
        output_path = Path(tdir) / "out.o"
        run_with_echo([TOOL_PREFIX + "objcopy", "-O", "binary", str(elf_path), str(output_path)])
        return output_path.read_bytes()


# == Main entrypoint == #
def main() -> None:
    try:
        arm9_image = Path(sys.argv[1])
    except IndexError:
        builtins.print(f"usage: {sys.argv[0]} <path to ARM9> <path to ARM7>", file=sys.stderr)
        sys.exit(1)

    arm7_image: Path | None = None
    with contextlib.suppress(IndexError):
        arm7_image = Path(sys.argv[2])

    if not arm9_image.exists():
        print(f"[red]no such file[/red]: {arm9_image}")
        sys.exit(1)

    if arm7_image and not arm7_image.exists():
        print(f"[red]no such file[/red]: {arm7_image}")
        sys.exit(1)

    try:
        with (Path.cwd() / "ndspacker.toml").open(mode="rb") as f:
            packer_settings = tomllib.load(f)
    except FileNotFoundError:
        packer_settings = DEFAULT_PACKER_SETTINGS

    # ARM9 binaries should always be in the ELF format as they're output from gcc/rustc.
    print("[cyan]reading ARM9 binary...[/cyan]")
    arm9_headers = get_elf_headers(elf_path=arm9_image)

    if (type := arm9_headers["machine"]) != "ARM":
        print(f"¿ this is [red]{type}[/red], not ARM ?")
        sys.exit(1)

    arm9_ep = int(arm9_headers["entry_point_address"][2:], 16)
    arm9_data = read_from_elf(arm9_image)

    print(f"[green]ok![/green] entrypoint is [magenta]0x{arm9_ep:0x}[/magenta]")
    print(f"ARM9 image size: [magenta]{len(arm9_data)}[/magenta] bytes")

    # ARM7 binaries can either be ELF if they're original, or NDS if they're stolen from
    # a ROM.
    arm7_ep: int
    arm7_data: bytes

    # borrowed_nds_logo: bytes = b""

    if arm7_image is not None:
        if arm7_image.suffix == ".nds":
            print("[cyan]stealing ARM7 rom image...[/cyan]")
            with arm7_image.open(mode="rb") as f:
                raw_data = f.read()
                arm7_ep, arm7_data = read_arm7_from_rom(raw_data)

                # print("[cyan]stealing official nitro logo...[/cyan]")
                # borrowed_nds_logo = raw_data[0xc0:0xc0 + 0x9c]

        else:
            print("[cyan]reading ARM7 binary...")
            arm7_ep = int(get_elf_headers(arm7_image)["entry_point_address"])
            arm7_data = read_from_elf(arm7_image)
    else:
        arm7_ep = 0x2380000
        # PC := PC
        arm7_data: bytes = b"\xfe\xff\xff\xea"

    print(f"[green]ok![/green] entrypoint is [magenta]0x{arm7_ep:0x}[/magenta]")
    print(f"ARM7 image size: [magenta]{len(arm7_data)}[/magenta] bytes")

    maker_code: str = packer_settings.get("maker_code", "01")
    game_code: str = packer_settings.get("game_code", "ABCD")
    game_title: str = packer_settings.get("game_title", "NITRO-SDK")

    with tempfile.TemporaryDirectory(suffix="ndspacker") as directory:
        saved_arm9 = Path(directory) / "arm9.tmp.bin"
        saved_arm7 = Path(directory) / "arm7.tmp.bin"
        saved_arm9.write_bytes(arm9_data)
        saved_arm7.write_bytes(arm7_data)

        # fmt: off
        run_with_echo([
            "ndstool",
            "-c", "./rom.nds",
            "-9", str(saved_arm9),
            "-7", str(saved_arm7),
            # passing -e9 also sets r9, for some reason, so overwrite it
            "-e9", str(arm9_ep), "-r9", "0x2000000", 
            "-e7", str(arm7_ep),
            # game info
            "-g", game_code, maker_code, game_title, "1",
        ])
        # fmt: on

        # This makes the DS firmware absolutely freak the fuck out!
        # if borrowed_nds_logo:
        #    print("[cyan]writing fixed logo...[/cyan]")
        #
        #    with open("./rom.nds", "rb+") as f:
        #        f.seek(0xC0)
        #        f.write(borrowed_nds_logo)
        #        f.write((0xCF56).to_bytes(length=2, byteorder="little"))


if __name__ == "__main__":
    main()
