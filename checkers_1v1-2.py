# meta developer: OpenAI
# scope: hikka_only
# requires: hikka

from .. import loader, utils
import random

@loader.tds
class CheckersMod(loader.Module):
    """Шашки 1 на 1 между пользователями Telegram"""
    strings = {"name": "Checkers"}

    def __init__(self):
        self.games = {}       # game_id -> game
        self.invites = {}     # target_id -> game_id
        self.user_game = {}   # user_id -> game_id
        self.next_id = 1

    def _new_board(self):
        b = [[None for _ in range(8)] for _ in range(8)]
        for r in range(3):
            for c in range(8):
                if (r + c) % 2:
                    b[r][c] = "b"
        for r in range(5, 8):
            for c in range(8):
                if (r + c) % 2:
                    b[r][c] = "w"
        return b

    def _draw(self, b):
        chars = {"w": "⚪", "b": "⚫", "W": "👑", "B": "👑"}
        out = ["    A  B  C  D  E  F  G  H"]
        for r in range(8):
            row = []
            for c in range(8):
                p = b[r][c]
                row.append(chars[p] if p else ("⬛" if (r+c)%2 else "⬜"))
            out.append(f"{r+1}  " + " ".join(row))
        return "\n".join(out)

    def _inside(self, r, c):
        return 0 <= r < 8 and 0 <= c < 8

    def _moves(self, b, color, captures_only=False):
        moves = []
        dirs = [(-1,-1), (-1,1), (1,-1), (1,1)]
        for r in range(8):
            for c in range(8):
                p = b[r][c]
                if p not in (color, color.upper()):
                    continue
                king = p.isupper()
                for dr, dc in dirs:
                    nr, nc = r + dr, c + dc
                    if self._inside(nr,nc):
                        if b[nr][nc] is None and not captures_only:
                            if king or (color == "w" and dr < 0) or (color == "b" and dr > 0):
                                moves.append((r,c,nr,nc,None))
                        jr, jc = r + 2*dr, c + 2*dc
                        if self._inside(jr,jc) and b[jr][jc] is None and b[nr][nc] and b[nr][nc].lower() != color:
                            moves.append((r,c,jr,jc,(nr,nc)))
        caps = [m for m in moves if m[4]]
        return caps if caps else moves

    def _parse(self, s):
        p = s.strip().lower().replace("-", " ").split()
        if len(p) != 2 or any(len(x) != 2 for x in p):
            return None
        try:
            c1, r1 = ord(p[0][0])-97, int(p[0][1])-1
            c2, r2 = ord(p[1][0])-97, int(p[1][1])-1
            if all(0 <= x < 8 for x in (r1,c1,r2,c2)):
                return r1,c1,r2,c2
        except Exception:
            pass
        return None

    def _name(self, user):
        return getattr(user, "username", None) and "@" + user.username or str(user.id)

    async def _get_target(self, message):
        users = await message.client.get_participants(message.to_id, limit=1) if False else []
        reply = await message.get_reply_message()
        if reply:
            return await message.client.get_entity(reply.sender_id)
        args = utils.get_args_raw(message).strip()
        if not args:
            return None
        try:
            return await message.client.get_entity(args.split()[0])
        except Exception:
            return None

    @loader.command()
    async def шашки(self, message):
        """Пригласить пользователя: .шашки @username (или ответом на его сообщение)"""
        me = await message.client.get_me()
        target = await self._get_target(message)
        if not target:
            await utils.answer(message, "❌ Укажи пользователя: `.шашки @username` или ответь на его сообщение.")
            return
        if target.id == me.id:
            await utils.answer(message, "❌ Нельзя играть самому с собой.")
            return
        if target.bot:
            await utils.answer(message, "❌ Нельзя пригласить бота.")
            return
        if target.id in self.user_game or me.id in self.user_game:
            await utils.answer(message, "❌ Один из игроков уже находится в партии.")
            return

        gid = str(self.next_id)
        self.next_id += 1
        self.games[gid] = {
            "board": self._new_board(),
            "white": me.id,
            "black": target.id,
            "turn": "w",
        }
        self.invites[target.id] = gid
        self.user_game[me.id] = gid
        await utils.answer(message, f"🎲 Приглашение отправлено {self._name(target)}.\n\n"
                           f"Чтобы принять игру, напиши ему: `.принять`")
        try:
            await message.client.send_message(
                target.id,
                f"🎲 {self._name(me)} приглашает тебя в шашки!\n"
                f"Напиши `.принять`, чтобы начать игру."
            )
        except Exception:
            pass

    @loader.command()
    async def принять(self, message):
        """Принять приглашение: .принять"""
        me = await message.client.get_me()
        gid = self.invites.pop(me.id, None)
        if not gid or gid not in self.games:
            await utils.answer(message, "❌ У тебя нет активного приглашения.")
            return
        g = self.games[gid]
        self.user_game[me.id] = gid
        board = self._draw(g["board"])
        text = f"🎲 Игра началась!\n⚪ Белые: {g['white']}\n⚫ Чёрные: {g['black']}\n\n{board}\n\nХод белых: `.ход A3 B4`"
        await utils.answer(message, text)
        try:
            await message.client.send_message(g["white"], text)
        except Exception:
            pass

    @loader.command()
    async def ход(self, message):
        """Сделать ход: .ход A3 B4"""
        uid = message.sender_id
        gid = self.user_game.get(uid)
        if not gid or gid not in self.games:
            await utils.answer(message, "❌ Ты не участвуешь в партии.")
            return
        g = self.games[gid]
        color = "w" if uid == g["white"] else "b"
        if g["turn"] != color:
            await utils.answer(message, "⏳ Сейчас ход соперника.")
            return

        mv = self._parse(utils.get_args_raw(message))
        if not mv:
            await utils.answer(message, "Формат: `.ход A3 B4`")
            return

        valid = [m for m in self._moves(g["board"], color) if m[:4] == mv]
        if not valid:
            await utils.answer(message, "❌ Такой ход невозможен.")
            return

        r,c,nr,nc,taken = valid[0]
        p = g["board"][r][c]
        g["board"][r][c] = None
        g["board"][nr][nc] = p
        if taken:
            g["board"][taken[0]][taken[1]] = None

        if p == "w" and nr == 0:
            g["board"][nr][nc] = "W"
        elif p == "b" and nr == 7:
            g["board"][nr][nc] = "B"

        opponent = "b" if color == "w" else "w"
        winner = uid if not g["board"] or not self._moves(g["board"], opponent) else None
        if winner:
            loser = g["black"] if winner == g["white"] else g["white"]
            text = f"🏆 Победитель: {winner}\n\n{self._draw(g['board'])}"
            await utils.answer(message, text)
            try:
                await message.client.send_message(loser, text)
            except Exception:
                pass
            self._close(gid)
            return

        g["turn"] = opponent
        turn_id = g["white"] if opponent == "w" else g["black"]
        text = self._draw(g["board"]) + "\n\n" + (
            "⚪ Ход белых" if opponent == "w" else "⚫ Ход чёрных"
        ) + ": `.ход A3 B4`"

        await utils.answer(message, text)
        other = g["black"] if uid == g["white"] else g["white"]
        try:
            await message.client.send_message(other, text)
        except Exception:
            pass

    def _close(self, gid):
        g = self.games.pop(gid, None)
        if not g:
            return
        self.user_game.pop(g["white"], None)
        self.user_game.pop(g["black"], None)

    @loader.command()
    async def поле(self, message):
        """Показать поле текущей партии"""
        gid = self.user_game.get(message.sender_id)
        if not gid or gid not in self.games:
            await utils.answer(message, "❌ Ты не участвуешь в партии.")
            return
        await utils.answer(message, self._draw(self.games[gid]["board"]))

    @loader.command()
    async def сдаться(self, message):
        """Сдаться в текущей партии"""
        gid = self.user_game.get(message.sender_id)
        if not gid or gid not in self.games:
            await utils.answer(message, "❌ Активной партии нет.")
            return
        g = self.games[gid]
        winner = g["black"] if message.sender_id == g["white"] else g["white"]
        loser = message.sender_id
        text = f"🏳️ Игрок {loser} сдался.\n🏆 Победитель: {winner}"
        await utils.answer(message, text)
        try:
            await message.client.send_message(winner, text)
        except Exception:
            pass
        self._close(gid)
