"""Brief history and evidence-only question answering routes."""
from fastapi import APIRouter, Request

from videobrief.application.question_answering import answer_from_brief
from videobrief.domain.errors import InputValidationError

from ..schemas import QuestionRequest

router = APIRouter(prefix="/api")


@router.get("/history")
def history(request: Request) -> list[dict]:
    return request.app.state.container.briefs.list_recent(30)


@router.get("/history/{brief_id}")
def history_item(brief_id: str, request: Request) -> dict:
    return request.app.state.container.briefs.get(brief_id)


@router.post("/briefs/{brief_id}/ask")
def ask_brief(brief_id: str, payload: QuestionRequest, request: Request) -> dict:
    question = payload.question.strip()
    if not question:
        raise InputValidationError("请输入想查找的问题。")
    brief = request.app.state.container.briefs.get(brief_id)
    return answer_from_brief(brief, question)
