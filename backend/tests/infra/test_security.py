from app.infra.security import hash_password, verify_password


def test_la_contrasena_no_se_guarda_en_claro_y_se_verifica():
    hashed = hash_password("Cotiza2026*")
    assert hashed != "Cotiza2026*"
    assert verify_password("Cotiza2026*", hashed)
    assert not verify_password("otra", hashed)


def test_dos_hashes_de_la_misma_contrasena_son_distintos():
    assert hash_password("secreto") != hash_password("secreto")
