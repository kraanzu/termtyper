from os import get_terminal_size
import time
from bisect import bisect
from rich.align import Align

from rich.text import Span, Text
from rich.panel import Panel
from textual.app import App
from textual.widget import Widget
from textual.message import Message, MessageTarget
from ...utils import chomsky, Parser


class UpdateRaceBar(Message, bubble=True):
    def __init__(self, sender: MessageTarget, completed: float, speed: float) -> None:
        super().__init__(sender)
        self.completed = completed
        self.speed = speed


class ResetBar(Message, bubble=True):
    pass


EMPTY_SPAN = Span(0, 0, "")


class Screen(Widget):
    def __init__(
        self,
    ):
        super().__init__()

        self._refresh_settings()
        self._reset_params()
        if self.cursor_buddy_speed:
            self.set_interval(
                60 / (5 * self.cursor_buddy_speed), self.move_cursor_buddy
            )

        self.set_interval(0.2, self._update_race_bar)

    def _refresh_settings(self):
        parser = Parser()
        self.set_paragraph()
        self.min_speed = int(parser.get_data("min_speed"))
        self.min_accuracy = int(parser.get_data("min_accuracy"))
        self.min_burst = int(parser.get_data("min_burst"))
        self.cursor_buddy_speed = int(parser.get_data("cursor_buddy_speed"))
        self.force_correct = parser.get_data("force_correct")
        self.tab_reset = parser.get_data("tab_reset")
        self.difficulty = parser.get_data("difficulty")
        self.blind_mode = parser.get_data("blind_mode")
        self.confidence_mode = parser.get_data("confidence_mode")
        self.single_line_words = parser.get_data("single_line_words")
        self.sound = parser.get_data("sound")
        self.caret_style = parser.get_data("caret_style")

        match self.caret_style:
            case "off":
                self.cursor_style = ""
            case "block":
                self.cursor_style = "reverse"
            case "underline":
                self.cursor_style = "underline"

    def _get_color(self, type: str):
        if self.blind_mode == "on":
            return "yellow"
        else:
            return "green" if type == "correct" else "red"

    def _reset_params(self):

        self.started = False
        self.finised = False
        self.failed = False
        self.speed = 0
        self.min_speed = 0
        self.cursor_position = 0
        self.cursor_buddy_position = 0
        self.correct_key_presses = 0
        self.total_key_presses = 0
        self.mistakes = 0

    def _update_speed_records(self):
        if self.speed == -1:
            return

        med = (float(Parser().get_data("med")) + self.speed) / 2
        Parser().set_data("med", str(med))

        low = min(float(Parser().get_data("low")), self.speed)
        Parser().set_data("low", str(low))

        high = max(float(Parser().get_data("high")), self.speed)
        Parser().set_data("high", str(high))

    def _update_measurements(self):
        self.raw_speed = (
            60 * self.correct_key_presses / (time.time() - self.start_time) / 5
        )
        self.accuracy = (self.correct_key_presses / self.total_key_presses) * 100
        self.speed = (self.accuracy / 100) * self.raw_speed
        self.progress = (self.correct_key_presses + self.mistakes) / len(
            self.paragraph.plain
        )

        if (
            (self.min_speed and self.speed < self.min_speed)
            or (self.min_accuracy and self.accuracy < self.min_accuracy)
            or self.failed
        ):
            self.finised = True
            self.failed = True
            self.speed = -1

    async def _update_race_bar(self):
        if self.started and not self.finised:
            self._update_measurements()
            await self.emit(
                UpdateRaceBar(
                    self,
                    self.progress,
                    self.speed,
                )
            )

            self.refresh()
        else:
            await self.emit(UpdateRaceBar(self, 0, 0))

    def move_cursor_buddy(self):
        if self.started:
            if self.cursor_buddy_position < self.paragraph_length - 1:
                self.cursor_buddy_position += 1
                self.refresh()

    async def reset_screen(self, restart_same=Parser().get_data("restart_same")):

        self._reset_params()
        if restart_same == "on":
            self.paragraph.spans = []
        else:
            self.set_paragraph()

        await self.emit(ResetBar(self))
        self.refresh()

    def set_paragraph(self):
        self.paragraph_size = Parser().get_data("paragraph_size")

        if self.paragraph_size == "teensy":
            times = 1
        elif self.paragraph_size == "small":
            times = 5
        elif self.paragraph_size == "big":
            times = 10
        else:
            times = 15

        paragraph = chomsky(times, get_terminal_size()[0] - 5)
        # paragraph = "hello peter ok ok ok :w"
        self.paragraph = Text(paragraph)
        self.paragraph_length = len(self.paragraph.plain)

        self.spaces = [i for i, j in enumerate(paragraph) if j == " "] + [
            self.paragraph_length
        ]
        self.correct = [False] * (self.paragraph_length + 1)
        self.refresh()

    def report(self):
        if self.failed:
            return "FAILED"
        else:
            style = "bold red"
            return (
                "\n"
                + f"[{style}]RAW SPEED[/{style}]            : {self.raw_speed:.2f} WPM"
                + "\n"
                + f"[{style}]CORRECTED SPEED[/{style}]      : {self.speed:.2f} WPM"
                + "\n"
                + f"[{style}]ACCURACY[/{style}]             : {self.accuracy:.2f} %"
                + "\n"
                + f"[{style}]TIME TAKEN[/{style}]           : {time.time() - self.start_time:.2f} seconds"
            )

    async def key_add(self, key: str):
        if key == "ctrl+i":  # TAB
            await self.reset_screen()

        if self.finised:
            return

        if self.sound:
            self.console.bell()

        if key == "ctrl+h":  # BACKSPACE
            if self.confidence_mode == "max":
                return

            if self.cursor_position:
                if (
                    self.confidence_mode == "on"
                    and self.paragraph.plain[self.cursor_position - 1] == " "
                ):
                    return

                if self.correct[self.cursor_position]:
                    self.correct_key_presses -= 1
                else:
                    self.mistakes -= 1

                self.cursor_position -= 1
                self.paragraph.spans.pop()

        elif len(key) == 1:
            self.total_key_presses += 1
            if key == " ":
                if self.paragraph.plain[self.cursor_position] != " ":
                    if self.force_correct == "off":
                        next_space = self.spaces[
                            bisect(self.spaces, self.cursor_position)
                        ]
                        difference = (
                            next_space - self.cursor_position + 1
                        )  # 1 for the next space
                        self.paragraph.spans.extend([EMPTY_SPAN] * difference)
                        self.cursor_position = next_space
                    else:
                        return
                else:
                    if self.difficulty == "expert" and self.mistakes:
                        self.failed = True

                    self.correct_key_presses += 1
                    self.paragraph.spans.append(EMPTY_SPAN)

            elif key == self.paragraph.plain[self.cursor_position]:
                self.paragraph.spans.append(
                    Span(
                        self.cursor_position,
                        self.cursor_position + 1,
                        self._get_color("correct"),
                    )
                )
                self.correct_key_presses += 1
                self.correct[self.cursor_position] = True

            else:
                if (
                    self.paragraph.plain[self.cursor_position] == " "
                    or self.force_correct == "on"
                ):
                    return

                self.paragraph.spans.append(
                    Span(
                        self.cursor_position,
                        self.cursor_position + 1,
                        self._get_color("mistake"),
                    )
                )

                self.mistakes += 1
                if self.difficulty == "master":
                    self.failed = True

            self.cursor_position += 1
            if not self.started:
                self.start_time = time.time()
            self.started = True

            if self.cursor_position == self.paragraph_length:
                await self._update_race_bar()
                self.finised = True

        self.refresh()

    def render(self):
        if not self.finised and not self.failed:
            return Panel(
                Text(
                    self.paragraph.plain,
                    spans=self.paragraph.spans
                    + [
                        Span(
                            self.cursor_position,
                            self.cursor_position + 1,
                            self.cursor_style,
                        )
                    ]
                    + [
                        Span(
                            self.cursor_buddy_position,
                            self.cursor_buddy_position + 1,
                            "reverse magenta",
                        )
                        if self.cursor_buddy_speed
                        else EMPTY_SPAN
                    ],
                )
            )

        else:
            self._update_speed_records()
            return Panel(Align.center(self.report(), vertical="middle"))


if __name__ == "__main__":

    class MyApp(App):
        async def on_mount(self):
            self.x = Screen()
            await self.view.dock(self.x)

    MyApp.run()