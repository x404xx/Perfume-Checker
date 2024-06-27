import asyncio
import re
from html import unescape

import httpx
import inquirer
from inquirer.themes import BlueComposure
from rich.box import HEAVY, HEAVY_EDGE
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from unidecode import unidecode
from user_agent import generate_user_agent

console = Console()
prompt = Prompt()

LOGO = """
░▒█▀▀▄░█▀▀▄░▀█▀░█▀▄░█░░░░░░▒█▀▀▄░█░░░░█▀▀░█▀▄░█░▄░█▀▀░█▀▀▄░░░
░▒█▀▀▄░█▄▄█░░█░░█░░░█▀▀█░░░▒█░░░░█▀▀█░█▀▀░█░░░█▀▄░█▀▀░█▄▄▀░▄▄
░▒█▄▄█░▀░░▀░░▀░░▀▀▀░▀░░▀░░░▒█▄▄▀░▀░░▀░▀▀▀░▀▀▀░▀░▀░▀▀▀░▀░▀▀░▀▀
                                BY:ˣ⁴⁰⁴ˣˣ"""


class ProgramLogo:
    @staticmethod
    def _setup_padding():
        padding = (console.width - max(len(line) for line in LOGO.split("\n"))) // 2
        return "\n".join(f"{' ' * padding}{line}" for line in LOGO.split("\n"))

    @classmethod
    def setup_logo(cls):
        console.print(
            Panel(
                f"[blue1]{cls._setup_padding()}[/]",
                border_style="deep_sky_blue3",
                box=HEAVY,
            ),
        )


class PerfumeBatch:
    BASE_URL = "https://www.checkfresh.com"
    BRAND_PATTERN = re.compile(
        r'<a[^>]*data-norm="([^"]*)"[^>]*lang="[^"]*">([^<]*)</a>'
    )
    HASH_PATTERN = re.compile(r'hash" value="(.*?)"')
    TABLE_PATTERN = re.compile(
        r"<td>([^<]+)</td>\s*<td>(?:<code>)?([^<]+)(?:<\/code>)?</td>"
    )

    @staticmethod
    def _format_brand_name(brand):
        return re.sub(
            r"[ .\'&]+", "-", re.sub(r"[^a-zA-Z0-9\s.'&]", "", unidecode(brand)).lower()
        )

    @classmethod
    async def _get_brand_names(cls, client):
        response = await client.get("/")
        if not response.is_success:
            console.print(f"[red]Failed to make a requests for '{cls.BASE_URL}'[/]")
            raise SystemExit(1)

        return [
            unescape(brand_name)
            for _, brand_name in cls.BRAND_PATTERN.findall(response.text)
        ]

    @classmethod
    async def _select_brand(cls, client):
        unescape_brand = await cls._get_brand_names(client)
        brand_prompt = [
            inquirer.List(
                "Brand",
                message=f"Found ({len(unescape_brand)}) brands! Select your brand choice",
                choices=unescape_brand,
            )
        ]
        if not (selection := inquirer.prompt(brand_prompt, theme=BlueComposure())):
            console.print("[red]No brand selected. Exiting...[/]")
            raise SystemExit(1)

        return cls._format_brand_name(selection["Brand"]), selection["Brand"]

    @classmethod
    async def _get_batch_data(cls, client, selected_brand, batch_code):
        response = await client.get(f"/{selected_brand}.html")
        if not response.is_success:
            console.print(f"[red]Failed to fetch brand data for '{selected_brand}'[/]")
            raise SystemExit(1)

        if not (hashes := cls.HASH_PATTERN.search(response.text)):
            console.print("[red]Hash value not found[/]")
            raise SystemExit(1)

        response = await client.post(
            f"/{selected_brand}.html", data={"batch": batch_code, "hash": hashes[1]}
        )
        if not response.is_success:
            console.print(f"[red]Failed to fetch batch data for '{selected_brand}'[/]")
            raise SystemExit(1)

        return {
            key.strip(): value.strip()
            for key, value in cls.TABLE_PATTERN.findall(response.text)
        }

    @staticmethod
    def _create_table(
        brand, batch_code, pro_date="Waiting for update...", age="Waiting for update..."
    ):
        table = Table(
            header_style="bold yellow",
            border_style="purple",
            box=HEAVY_EDGE,
            expand=True,
        )
        table.add_column("Brand", style="dodger_blue2", justify="center")
        table.add_column("Batch Code", style="blue1", justify="center")
        table.add_column("Production Date", style="blue_violet", justify="center")
        table.add_column("Age", style="blue", justify="center")
        table.add_row(brand, batch_code, pro_date, age)
        return table

    @classmethod
    def _display_batch_info(cls, live, brand, batch_code, batch_data):
        live.update(
            cls._create_table(
                brand,
                batch_code,
                batch_data.get("Production date", "Waiting for update..."),
                batch_data.get("Age", "Waiting for update..."),
            )
        )

    @classmethod
    async def start_check(cls):
        console.clear()
        ProgramLogo.setup_logo()
        async with httpx.AsyncClient(
            base_url=cls.BASE_URL,
            headers={"User-Agent": generate_user_agent()},
            timeout=10,
        ) as client:
            try:
                selected_brand, selection = await cls._select_brand(client)
                batch_code = prompt.ask("[pale_green3]Your Batch Code[/] ")
                print("\033[F\033[K")

                initial_table = cls._create_table(unidecode(selection), batch_code)
                with Live(
                    initial_table, console=console, refresh_per_second=10
                ) as live:
                    batch_data = await cls._get_batch_data(
                        client, selected_brand, batch_code
                    )
                    cls._display_batch_info(
                        live, unidecode(selection), batch_code, batch_data
                    )
                console.print()
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                console.print(f"[red]An error occurred: {e}[/]")
            except SystemExit:
                pass


if __name__ == "__main__":
    asyncio.run(PerfumeBatch.start_check())
