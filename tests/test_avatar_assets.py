from io import BytesIO
import pytest
from PIL import Image
from scripts.migrate_avatars import variants, public_url
from app.services.avatar_assets import avatar_variants, CACHE_CONTROL

def test_webp_preserves_aspect_and_bounds():
    source = BytesIO()
    Image.new("RGB", (1000, 800), "red").save(source, format="PNG")
    output = variants(source.getvalue())
    assert set(output) == {128,256,512}
    for size, data in output.items():
        im = Image.open(BytesIO(data))
        assert im.format == "WEBP"
        assert im.width == size
        assert abs(im.height / im.width - .8) < .01
        assert im.getexif() == {}

def test_small_image_not_upscaled():
    source = BytesIO()
    Image.new("RGBA", (40,60)).save(source, format="PNG")
    for data in variants(source.getvalue()).values():
        assert Image.open(BytesIO(data)).size == (40,60)

def test_variants_only_our_versioned_storage(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3","https://storage.example.test")
    monkeypatch.setenv("AVATAR_BUCKET","avatars")
    base = "https://storage.example.test/avatars/avatars/v1/1/" + "a"*32 + "/"
    assert avatar_variants(base+"512.webp") == {str(s):base+f"{s}.webp" for s in (128,256,512)}
    assert avatar_variants("https://other.test/512.webp") == {}
    assert avatar_variants(base+"original") == {}
    assert "immutable" in CACHE_CONTROL

def test_rejects_local_sources():
    with pytest.raises(ValueError, match="non_public"):
        public_url("http://127.0.0.1/image")
    with pytest.raises(ValueError):
        public_url("file:///etc/passwd")
