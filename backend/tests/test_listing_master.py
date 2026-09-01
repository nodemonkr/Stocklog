from backend.app.listing_master import merge_company_master, parse_kind_company_html


def test_parse_kind_company_html_preserves_leading_zero_code():
    html="""
    <table><tr><th>회사명</th><th>종목코드</th><th>업종</th></tr>
    <tr><td>한글과컴퓨터</td><td>030520</td><td>소프트웨어 개발 및 공급업</td></tr>
    <tr><td>삼성전자</td><td>005930</td><td>전자부품 제조업</td></tr></table>
    """
    rows=parse_kind_company_html(html,"KOSDAQ")
    assert rows[0]["code"]=="030520"
    assert rows[0]["name"]=="한글과컴퓨터"
    assert rows[0]["name_verified"] is True


def test_kind_master_fills_company_omitted_by_kiwoom_snapshot():
    primary=[{"code":"005930","name":"삼성전자","market":"KOSPI"}]
    kind=[
        {"code":"005930","name":"삼성전자","market":"KOSPI"},
        {"code":"030520","name":"한글과컴퓨터","market":"KOSDAQ"},
    ]
    merged,stats=merge_company_master(primary,kind)
    by_code={x["code"]:x for x in merged}
    assert "030520" in by_code
    assert by_code["030520"]["market"]=="KOSDAQ"
    assert stats["kind_added_missing_from_primary"]==1


def test_verified_krx_official_rename_preserves_old_name_as_alias():
    primary=[{"code":"030520","name":"한글과컴퓨터","market":"KOSDAQ"}]
    kind=[{"code":"030520","name":"한컴","market":"KOSDAQ","name_verified":True}]
    merged,stats=merge_company_master(primary,kind)
    row={x["code"]:x for x in merged}["030520"]
    assert row["name"]=="한컴"
    assert "한글과컴퓨터" in row["name_aliases"]
    assert row["name_source"]=="KRX_KIND"
    assert stats["official_name_changes"]==1


def test_unverified_kind_parse_cannot_overwrite_trusted_name():
    primary=[{"code":"030520","name":"한글과컴퓨터","market":"KOSDAQ"}]
    kind=[{"code":"030520","name":"엉뚱한값","market":"KOSDAQ","name_verified":False}]
    merged,stats=merge_company_master(primary,kind)
    row={x["code"]:x for x in merged}["030520"]
    assert row["name"]=="한글과컴퓨터"
    assert stats["unverified_name_overwrites_blocked"]==1
