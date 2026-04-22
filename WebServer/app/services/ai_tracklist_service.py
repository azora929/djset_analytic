from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from ..core.config import AI_TRACKLIST_SYSTEM_PROMPT, OPENAI_API_KEY, OPENAI_MODEL


class CleanState(TypedDict):
    raw_text: str
    cleaned_text: str


@dataclass(slots=True)
class CleanResult:
    cleaned_text: str
    cleaned_tracks: list[str]
    used_ai: bool


def _extract_text(response: Any) -> str:
    text = getattr(response, "output_text", "") or ""
    if text:
        return text.strip()

    output = getattr(response, "output", None)
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for chunk in content:
                    chunk_text = getattr(chunk, "text", None)
                    if isinstance(chunk_text, str):
                        chunks.append(chunk_text)
        if chunks:
            return "\n".join(chunks).strip()
    return ""


def _clean_with_openai(state: CleanState) -> CleanState:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY не задан.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    user_prompt = f"Сырой список распознаваний:\n{state['raw_text']}\n"

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=user_prompt,
            tools=[{"type": "web_search"}],
            instructions=AI_TRACKLIST_SYSTEM_PROMPT
        )
    except Exception:
        # Фолбэк, если у модели/аккаунта не включен web search tool.
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=user_prompt,
            instructions=AI_TRACKLIST_SYSTEM_PROMPT
        )

    cleaned_text = _extract_text(response)
    if not cleaned_text:
        raise RuntimeError("LLM вернула пустой ответ при очистке треклиста.")
    state["cleaned_text"] = cleaned_text
    return state


def clean_tracklist_with_ai(raw_text: str) -> CleanResult:
    if not raw_text.strip():
        return CleanResult(cleaned_text="Очищенный треклист\n", cleaned_tracks=[], used_ai=False)

    graph = StateGraph(CleanState)
    graph.add_node("clean_with_openai", _clean_with_openai)
    graph.add_edge(START, "clean_with_openai")
    graph.add_edge("clean_with_openai", END)
    chain = graph.compile()

    result = chain.invoke(
        {
            "raw_text": raw_text,
            "cleaned_text": "",
        }
    )
    cleaned_text = result.get("cleaned_text", "").strip()
    if not cleaned_text:
        return CleanResult(cleaned_text="Очищенный треклист\n", cleaned_tracks=[], used_ai=False)
    # Текст сохраняем 1-в-1 как вернула нейросеть, без локального пост-парсинга.
    return CleanResult(cleaned_text=cleaned_text, cleaned_tracks=[], used_ai=True)
