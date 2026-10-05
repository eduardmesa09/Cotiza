def test_health_responde_ok_con_base_de_datos_accesible(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
