from django.core.management.base import BaseCommand, CommandError

from rag.llm import LLMError, get_llm


class Command(BaseCommand):
    help = "Send a single prompt to the configured LLM and stream the reply (smoke test)."

    def add_arguments(self, parser):
        parser.add_argument("prompt", nargs="+", help="Prompt text")

    def handle(self, *args, **opts):
        messages = [{"role": "user", "content": " ".join(opts["prompt"])}]
        try:
            for token in get_llm().stream_chat(messages):
                self.stdout.write(token, ending="")
                self.stdout.flush()
        except LLMError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write("")
