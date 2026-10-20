"""Server-rendered page shells; all data comes from the JSON API."""

from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("web", __name__, template_folder="templates", static_folder="static",
               static_url_path="/assets")


@bp.get("/")
def library():
    return render_template("library.html", page="library")


@bp.get("/watch/<video_id>")
def watch(video_id: str):
    return render_template("watch.html", page="watch", video_id=video_id)


@bp.get("/upload")
def upload():
    return render_template("upload.html", page="upload")


@bp.get("/studio")
def studio():
    return render_template("studio.html", page="studio")


@bp.get("/login")
def login():
    return render_template("login.html", page="login")
