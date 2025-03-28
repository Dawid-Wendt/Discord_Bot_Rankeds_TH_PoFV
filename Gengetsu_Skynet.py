import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
from discord.ui import Button, View
from datetime import datetime

# Podstawowa konfiguracja bota z intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Połączenie z MongoDB
client = MongoClient("Serwer MongoDB")
db = client["PoFVrankeds"]
players_collection = db["players"]
matches_collection = db["matches"]

# Lista dostępnych postaci
POSTACIE = ["Reimu", "Marisa", "Sakuya", "Youmu", "Reisen", "Cirno", "Lyrica", "Merlin",
              "Lunasa", "Mystia", "Tewi", "Aya", "Medicine", "Yuuka", "Komachi", "Eiki"]


# Komenda do rejestracji gracza w systemie rankingowym
@bot.tree.command(name="rejestracja", description="Zarejestruj się w systemie rankingowym")
async def rejestracja(interaction: discord.Interaction):
    existing_player = players_collection.find_one({"user_id": interaction.user.id})

    if existing_player:
        await interaction.response.send_message("Jesteś już zarejestrowany w systemie rankingowym!", ephemeral=True)
        return

    players_collection.insert_one({
        "user_id": interaction.user.id,
        "username": interaction.user.display_name,  # Zapisz aktualną nazwę użytkownika
        "elo": 1000,
    })

    await interaction.response.send_message(
        "Rejestracja zakończona sukcesem! Teraz możesz korzystać z systemu rankingowego.", ephemeral=True)


# Komenda do wyświetlania rankingu
@bot.tree.command(name="ranking", description="Wyświetl ranking graczy według ELO")
async def ranking(interaction: discord.Interaction):
    players = players_collection.find().sort("elo", -1)
    ranking_text = "🏆 **Ranking graczy** 🏆\n"
    rank = 1
    for player in players:
        username = player.get("username", "Nieznany gracz")
        ranking_text += f"{rank}. {username} - ELO: {player['elo']}\n"
        rank += 1

    await interaction.response.send_message(ranking_text, ephemeral=True)


# Komenda do wyświetlania statystyk postaci, z opcją wyświetlenia najlepszych graczy
@bot.tree.command(name="statystyki_postaci", description="Wyświetl statystyki wybranej postaci")
@app_commands.describe(postac="Wybierz postać, której statystyki chcesz sprawdzić",
                       najlepsi_gracze="Wybierz kryterium dla najlepszych graczy")
@app_commands.choices(postac=[app_commands.Choice(name=char, value=char) for char in POSTACIE],
                      najlepsi_gracze=[
                          app_commands.Choice(name="wg liczby gier", value="by_number_of_games"),
                          app_commands.Choice(name="wg wskaźnika zwycięstw", value="by_winratio")
                      ])
async def statystyki_postaci(interaction: discord.Interaction, postac: str, najlepsi_gracze: str = None):
    rozegrane_rundy = 0
    wygrane_rundy = 0
    przegrane_rundy = 0
    statystyki_graczy = {}

    # Oblicz statystyki dla postaci i zbierz dane graczy
    for match in matches_collection.find({"$or": [{"character_1": postac}, {"character_2": postac}]}):
        score = match["score"].split(":")
        player_1_wins = int(score[0])
        player_2_wins = int(score[1])

        # Zlicz wszystkie rundy dla postaci
        rozegrane_rundy += player_1_wins + player_2_wins

        if match["character_1"] == postac:
            player_id = match["player_1_id"]
            won_rounds = player_1_wins
            lost_rounds = player_2_wins
        else:
            player_id = match["player_2_id"]
            won_rounds = player_2_wins
            lost_rounds = player_1_wins

        # Aktualizacja liczby wygranych/przegranych rund
        wygrane_rundy += won_rounds
        przegrane_rundy += lost_rounds

        # Aktualizacja statystyk dla gracza
        if player_id not in statystyki_graczy:
            statystyki_graczy[player_id] = {"gry": 0, "wygrane_rundy": 0, "przegrane_rundy": 0,
                                            "nazwa_gracza": match.get("player_1_name") if match[
                                                                                              "player_1_id"] == player_id else match.get(
                                                "player_2_name")}

        statystyki_graczy[player_id]["gry"] += 1
        statystyki_graczy[player_id]["wygrane_rundy"] += won_rounds
        statystyki_graczy[player_id]["przegrane_rundy"] += lost_rounds

    win_ratio = (wygrane_rundy / rozegrane_rundy * 100) if rozegrane_rundy > 0 else 0

    # Podstawowe statystyki postaci
    stats_text = (
        f"📈 **Statystyki postaci {postac}** 📈\n"
        f"Rozegrane rundy: {rozegrane_rundy}\n"
        f"Wygrane rundy: {wygrane_rundy}\n"
        f"Przegrane rundy: {przegrane_rundy}\n"
        f"Wskaźnik zwycięstw (rundy): {win_ratio:.2f}%\n"
    )

    # Wyświetlenie najlepszych graczy, jeśli `najlepsi_gracze` jest ustawione
    if najlepsi_gracze:
        if najlepsi_gracze == "by_number_of_games":
            sorted_players = sorted(
                statystyki_graczy.items(),
                key=lambda item: item[1]["gry"],
                reverse=True
            )
            top_text = "\n🏅 **Najlepsi gracze (wg liczby gier)**:\n"
        elif najlepsi_gracze == "by_winratio":
            sorted_players = sorted(
                statystyki_graczy.items(),
                key=lambda item: (
                            item[1]["wygrane_rundy"] / max(1, item[1]["wygrane_rundy"] + item[1]["przegrane_rundy"])),
                reverse=True
            )
            top_text = "\n🏅 **Najlepsi gracze (wg wskaźnika zwycięstw)**:\n"

        for player_id, stats in sorted_players[:5]:  # Pokaż top 5 graczy
            player = interaction.guild.get_member(player_id)
            player_name = player.display_name if player else statystyki_graczy[player_id]["nazwa_gracza"]
            player_win_ratio = (stats["wygrane_rundy"] / (stats["wygrane_rundy"] + stats["przegrane_rundy"]) * 100) if \
            stats["wygrane_rundy"] + stats["przegrane_rundy"] > 0 else 0
            top_text += (
                f"{player_name}: {stats['gry']} gier, "
                f"{stats['wygrane_rundy']} wygranych rund, "
                f"{stats['przegrane_rundy']} przegranych rund, "
                f"Wskaźnik zwycięstw: {player_win_ratio:.2f}%\n"
            )
        stats_text += top_text

    await interaction.response.send_message(stats_text, ephemeral=True)

@bot.tree.command(name="statystyki_gracza", description="Wyświetl statystyki gracza")
@app_commands.describe(gracz="Gracz, którego statystyki chcesz sprawdzić", postac="Opcjonalnie: postać, której statystyki chcesz sprawdzić")
@app_commands.choices(postac=[app_commands.Choice(name=char, value=char) for char in POSTACIE])
async def statystyki_gracza(interaction: discord.Interaction, gracz: discord.User, postac: str = None):
    # Sprawdzenie, czy gracz jest zarejestrowany
    player_data = players_collection.find_one({"user_id": gracz.id})
    if not player_data:
        await interaction.response.send_message("Ten gracz nie jest zarejestrowany w systemie rankingowym.", ephemeral=True)
        return

    # Filtruj mecze dla gracza i wybranej postaci (jeśli podano)
    filter_query = {"$or": [{"player_1_id": gracz.id}, {"player_2_id": gracz.id}]}
    if postac:
        filter_query["$or"].append({"character_1": postac})
        filter_query["$or"].append({"character_2": postac})

    matches = list(matches_collection.find(filter_query))
    if not matches:
        await interaction.response.send_message("Brak statystyk dla tego gracza.", ephemeral=True)
        return

    # Zlicz wygrane i przegrane rundy
    wygrane_rundy = 0
    przegrane_rundy = 0
    total_rundy = 0

    for match in matches:
        score = match["score"].split(":")
        player_1_wins = int(score[0])
        player_2_wins = int(score[1])

        # Rachunek rund w zależności od pozycji gracza i wybranej postaci
        if match["player_1_id"] == gracz.id:
            wygrane_rundy += player_1_wins
            przegrane_rundy += player_2_wins
        elif match["player_2_id"] == gracz.id:
            wygrane_rundy += player_2_wins
            przegrane_rundy += player_1_wins

        total_rundy += player_1_wins + player_2_wins

    win_ratio = (wygrane_rundy / total_rundy * 100) if total_rundy > 0 else 0

    stats_text = (
        f"📊 **Statystyki gracza {gracz.display_name}** 📊\n"
        f"Wygrane rundy: {wygrane_rundy}\n"
        f"Przegrane rundy: {przegrane_rundy}\n"
        f"Łączna liczba rund: {total_rundy}\n"
        f"Wskaźnik zwycięstw (rundy): {win_ratio:.2f}%\n"
    )
    if postac:
        stats_text = f"📊 **Statystyki gracza {gracz.display_name} dla postaci {postac}** 📊\n" + stats_text

    await interaction.response.send_message(stats_text, ephemeral=True)


@bot.tree.command(name="historia_meczy", description="Wyświetl historię meczów gracza")
@app_commands.describe(gracz="Gracz, którego historię meczów chcesz zobaczyć", postac="Opcjonalnie: postać, którą chcesz filtrować")
@app_commands.choices(postac=[app_commands.Choice(name=char, value=char) for char in POSTACIE])
async def historia_meczy(interaction: discord.Interaction, gracz: discord.User, postac: str = None):
    # Sprawdzenie, czy gracz jest zarejestrowany
    player_data = players_collection.find_one({"user_id": gracz.id})
    if not player_data:
        await interaction.response.send_message("Ten gracz nie jest zarejestrowany w systemie rankingowym.", ephemeral=True)
        return

    # Budowanie zapytania do MongoDB
    filter_query = {"$or": [{"player_1_id": gracz.id}, {"player_2_id": gracz.id}]}
    if postac:
        filter_query["$or"].append({"character_1": postac})
        filter_query["$or"].append({"character_2": postac})

    # Pobranie meczów z opcjonalnym filtrem po postaci
    matches = list(matches_collection.find(filter_query).sort("date", -1))
    if len(matches) == 0:
        await interaction.response.send_message("Brak historii meczów dla tego gracza.", ephemeral=True)
        return

    # Tworzenie tekstu historii meczów
    history_text = f"📜 **Historia meczów gracza {gracz.display_name}** 📜\n"
    if postac:
        history_text = f"📜 **Historia meczów gracza {gracz.display_name} grającego postacią {postac}** 📜\n"

    for match in matches:
        opponent_name = match["player_2_name"] if match["player_1_id"] == gracz.id else match["player_1_name"]
        player_character = match["character_1"] if match["player_1_id"] == gracz.id else match["character_2"]
        opponent_character = match["character_2"] if match["player_1_id"] == gracz.id else match["character_1"]
        winner = "Wygrał: " + (match["player_1_name"] if match["winner_id"] == match["player_1_id"] else match["player_2_name"])
        score = match["score"]
        date = match["date"].strftime("%Y-%m-%d %H:%M:%S")
        history_text += (
            f"- Przeciwnik: {opponent_name}, Wynik: {score}, {winner}, "
            f"Postać gracza: {player_character}, Postać przeciwnika: {opponent_character}, Data: {date}\n"
        )

    await interaction.response.send_message(history_text, ephemeral=True)


# Funkcja do obliczania ELO na podstawie liczby wygranych rund
def calculate_elo(player_elo, opponent_elo, player_wins, opponent_wins, k=32):
    total_rounds = player_wins + opponent_wins
    expected_score_player = player_wins / total_rounds
    elo_change = k * (expected_score_player - 0.5)  # Zmiana ELO na podstawie przewagi wygranych rund
    new_player_elo = player_elo + elo_change
    new_opponent_elo = opponent_elo - elo_change
    return round(new_player_elo), round(new_opponent_elo)


# Funkcja do aktualizacji ELO po złożeniu raportu
async def update_elo_after_match(player_1_id, player_2_id, player_1_wins, player_2_wins):
    player_1_data = players_collection.find_one({"user_id": player_1_id})
    player_2_data = players_collection.find_one({"user_id": player_2_id})

    player_1_elo = player_1_data.get("elo", 1000)
    player_2_elo = player_2_data.get("elo", 1000)

    # Obliczenie nowych wartości ELO dla graczy na podstawie liczby wygranych rund
    new_player_1_elo, new_player_2_elo = calculate_elo(player_1_elo, player_2_elo, player_1_wins, player_2_wins)

    # Aktualizacja wartości ELO w bazie danych
    players_collection.update_one({"user_id": player_1_id}, {"$set": {"elo": new_player_1_elo}})
    players_collection.update_one({"user_id": player_2_id}, {"$set": {"elo": new_player_2_elo}})


# Widok do obsługi raportu
class ReportMatchView(View):
    def __init__(self, interaction, opponent):
        super().__init__(timeout=180)  # 3 minuty na wypełnienie raportu
        self.interaction = interaction
        self.opponent = opponent
        self.result = None
        self.player_character = None
        self.opponent_character = None
        self.user = interaction.user  # Ustawienie użytkownika, który zgłosił komendę

    async def on_timeout(self):
        await self.interaction.delete_original_response()  # Usuń wiadomość po upływie czasu

    # Wybór wyniku meczu
    async def start_result_selection(self):
        view = View()
        results = ["2:0", "2:1", "1:2", "0:2"]
        for res in results:
            button = Button(label=res, style=discord.ButtonStyle.secondary)

            async def result_callback(interaction, res=res):
                if interaction.user != self.user:
                    await interaction.response.send_message("Tylko zgłaszający może wybrać wynik.", ephemeral=True)
                    return
                self.result = res
                await interaction.response.send_message(f"Wynik wybrany: {self.result}", ephemeral=True)
                await self.start_player_character_selection()

            button.callback = result_callback
            view.add_item(button)
        await self.interaction.followup.send("Wybierz wynik meczu:", view=view, ephemeral=True)

    # Wybór postaci zgłaszającego gracza
    async def start_player_character_selection(self):
        view = View()
        for character in POSTACIE:
            button = Button(label=character, style=discord.ButtonStyle.secondary)

            async def player_character_callback(interaction, character=character):
                if interaction.user != self.user:
                    await interaction.response.send_message("Tylko zgłaszający może wybrać postać.", ephemeral=True)
                    return
                self.player_character = character
                await interaction.response.send_message(f"Twoja postać: {self.player_character}", ephemeral=True)
                await self.start_opponent_character_selection()

            button.callback = player_character_callback
            view.add_item(button)
        await self.interaction.followup.send("Wybierz swoją postać:", view=view, ephemeral=True)

    # Wybór postaci przeciwnika
    async def start_opponent_character_selection(self):
        view = View()
        for character in POSTACIE:
            button = Button(label=character, style=discord.ButtonStyle.secondary)

            async def opponent_character_callback(interaction, character=character):
                if interaction.user != self.user:
                    await interaction.response.send_message("Tylko zgłaszający może wybrać postać przeciwnika.",
                                                            ephemeral=True)
                    return
                self.opponent_character = character
                await interaction.response.send_message(f"Postać przeciwnika: {self.opponent_character}",
                                                        ephemeral=True)
                await self.confirm_report()

            button.callback = opponent_character_callback
            view.add_item(button)
        await self.interaction.followup.send("Wybierz postać przeciwnika:", view=view, ephemeral=True)

    # Potwierdzenie raportu
    async def confirm_report(self):
        confirm_view = View()
        confirm_view.add_item(Button(label="Potwierdź raport", style=discord.ButtonStyle.success))
        confirm_view.add_item(Button(label="Anuluj", style=discord.ButtonStyle.danger))

        async def confirm_callback(interaction: discord.Interaction):
            if interaction.user != self.user:
                await interaction.response.send_message("Tylko zgłaszający może potwierdzić raport.", ephemeral=True)
                return

            # Usuwanie przycisku i kończenie widoku po pierwszym potwierdzeniu
            for item in confirm_view.children:
                item.disabled = True
            try:
                # Próbujemy edytować wiadomość, aby zdezaktywować przyciski
                await interaction.message.edit(view=confirm_view)
            except discord.NotFound:
                # Jeśli wiadomość już nie istnieje, ignorujemy błąd
                print("Wiadomość nie istnieje, nie można jej edytować.")

            await self.finalize_report(interaction)
            await self.interaction.delete_original_response()  # Usuń wiadomość po zatwierdzeniu raportu

            # Wysłanie wiadomości do przeciwnika z możliwością potwierdzenia
            opponent_view = View()
            opponent_view.add_item(Button(label="Potwierdź", style=discord.ButtonStyle.success))
            opponent_view.add_item(Button(label="Odrzuć", style=discord.ButtonStyle.danger))

            async def opponent_confirm_callback(interaction):
                if interaction.user != self.opponent:
                    await interaction.response.send_message("Tylko przeciwnik może potwierdzić raport.", ephemeral=True)
                    return

                # Wyciągnij ELO graczy i oblicz nowe wartości na podstawie rund
                player1_data = players_collection.find_one({"user_id": self.user.id})
                player2_data = players_collection.find_one({"user_id": self.opponent.id})

                player1_elo = player1_data["elo"]
                player2_elo = player2_data["elo"]
                player_1_wins, player_2_wins = map(int, self.result.split(":"))

                # Oblicz ELO na podstawie liczby wygranych rund
                new_player1_elo, new_player2_elo = calculate_elo(player1_elo, player2_elo, player_1_wins, player_2_wins)

                # Aktualizacja ELO dla obu graczy
                players_collection.update_one({"user_id": self.user.id}, {"$set": {"elo": new_player1_elo}})
                players_collection.update_one({"user_id": self.opponent.id}, {"$set": {"elo": new_player2_elo}})
                winner_id = self.user.id if player_1_wins > player_2_wins else self.opponent.id

                # Zapisz mecz do MongoDB
                matches_collection.insert_one({
                    "player_1_id": self.user.id,
                    "player_1_name": self.user.display_name,
                    "player_2_id": self.opponent.id,
                    "player_2_name": self.opponent.display_name,
                    "score": self.result,
                    "winner_id": winner_id,
                    "character_1": self.player_character,
                    "character_2": self.opponent_character,
                    "date": datetime.utcnow()
                })
                await interaction.response.send_message("Raport potwierdzony, mecz zapisany.", ephemeral=True)
                await interaction.message.delete()  # Usuń wiadomość po zatwierdzeniu przez przeciwnika

            async def opponent_reject_callback(interaction):
                if interaction.user != self.opponent:
                    await interaction.response.send_message("Tylko przeciwnik może odrzucić raport.", ephemeral=True)
                    return
                await interaction.response.send_message("Raport odrzucony. Mecz nie został zapisany.", ephemeral=True)
                await interaction.message.delete()  # Usuń wiadomość po odrzuceniu przez przeciwnika

            opponent_view.children[0].callback = opponent_confirm_callback
            opponent_view.children[1].callback = opponent_reject_callback

            await self.interaction.channel.send(
                content=f"{self.opponent.mention}, {self.user.display_name} zgłosił mecz:\n"
                        f"Wynik: {self.result}\n"
                        f"Twoja postać: {self.opponent_character}\n"
                        f"Postać przeciwnika: {self.player_character}",
                view=opponent_view)

        async def cancel_callback(interaction: discord.Interaction):
            if interaction.user != self.user:
                await interaction.response.send_message("Tylko zgłaszający może anulować raport.", ephemeral=True)
                return
            await interaction.response.send_message("Raport został anulowany.", ephemeral=True)
            await self.interaction.delete_original_response()  # Usuń wiadomość po anulowaniu

        confirm_view.children[0].callback = confirm_callback
        confirm_view.children[1].callback = cancel_callback

        await self.interaction.followup.send(
            f"Podsumowanie raportu:\n"
            f"Przeciwnik: {self.opponent.display_name}\n"
            f"Wynik: {self.result}\n"
            f"Twoja postać: {self.player_character}\n"
            f"Postać przeciwnika: {self.opponent_character}",
            view=confirm_view, ephemeral=True
        )

    # Finalizacja raportu
    async def finalize_report(self, interaction):
        await interaction.response.send_message("Raport zakończony.", ephemeral=True)
        self.stop()  # Zakończ widok

# Komenda do rozpoczęcia raportowania meczu
@bot.tree.command(name="raport", description="Zgłoś wynik meczu")
@app_commands.describe(przeciwnik="Gracz, z którym grałeś")
async def raport(interaction: discord.Interaction, przeciwnik: discord.User):
    # Sprawdzenie, czy gracz nie zgłasza meczu z samym sobą
    if przeciwnik == interaction.user:
        await interaction.response.send_message("Nie możesz zgłosić meczu z samym sobą!", ephemeral=True)
        return

    # Sprawdzenie, czy zgłaszający jest zarejestrowany
    user_data = players_collection.find_one({"user_id": interaction.user.id})
    if not user_data:
        await interaction.response.send_message("Musisz się najpierw zarejestrować w systemie rankingowym.", ephemeral=True)
        return

    # Sprawdzenie, czy przeciwnik jest zarejestrowany
    opponent_data = players_collection.find_one({"user_id": przeciwnik.id})
    if not opponent_data:
        await interaction.response.send_message("Twój przeciwnik nie jest zarejestrowany w systemie rankingowym.", ephemeral=True)
        return

    view = ReportMatchView(interaction, przeciwnik)
    await interaction.response.send_message("Rozpoczynam proces raportowania meczu.", view=view, ephemeral=True)
    await view.start_result_selection()  # Rozpocznij od wyboru wyniku



# Rejestracja komend aplikacji
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()  # Synchronizuje komendy slash z serwerem
        print(f"Bot połączony. Zsynchronizowano {len(synced)} komend.")
    except Exception as e:
        print(f"Błąd podczas synchronizacji komend: {e}")

# Uruchomienie bota
bot.run('Klucz Bota Discordowego')
