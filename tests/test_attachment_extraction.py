import io
import zipfile

from attachments import AttachmentInput, extract_attachment


def test_text_attachment_is_extracted_and_clipped_safely():
    result = extract_attachment(AttachmentInput(b"alpha\nbeta", "text/plain", "notes.txt"))
    assert result.kind == "text"
    assert "alpha" in result.context
    assert "beta" in result.context


def test_docx_attachment_extracts_document_xml():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<document xmlns="urn:test"><body><p><t>Hello DOCX</t></p></body></document>',
        )
    result = extract_attachment(AttachmentInput(buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "report.docx"))
    assert result.kind == "docx"
    assert "Hello DOCX" in result.text


def test_apk_is_inspected_as_archive_not_executed():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"binary manifest")
        archive.writestr("classes.dex", b"not executed")
    result = extract_attachment(AttachmentInput(buffer.getvalue(), "application/vnd.android.package-archive", "sample.apk"))
    assert result.kind == "apk"
    assert result.metadata["ZIP_MEMBERS"] == 2
    assert "classes.dex" in result.metadata["ZIP_SAMPLE"]


def test_video_and_audio_return_metadata_without_claiming_transcription():
    audio = extract_attachment(AttachmentInput(b"not wav", "audio/mpeg", "clip.mp3"))
    video = extract_attachment(AttachmentInput(b"video", "video/mp4", "clip.mp4"))
    assert audio.available is False
    assert video.available is False
    assert "optional" in video.context.lower()
