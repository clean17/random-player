from pathlib import Path


src_folder = Path(r"C:\Users\user\Downloads\20260904_sns_laris_migration")
dst_folder = src_folder / "with_header"

dst_folder.mkdir(exist_ok=True)

HEADER = ("tno_reg_user_id,tdd_reg,tno_upd_user_id,tdd_upd,tno_sns_collect_data_blob_id,tno_sns_collect_data_id,"
          "tbe_sns_collect_data_blob_cont,tnr_del,tbe_sns_collect_data_clob_cont")

# for file in src_folder.glob("*.csv"):
for file in src_folder.glob("batch_data_TB_INF_SNS_COLLECT_DATA_BLOB_*.csv"):
    data = file.read_bytes()

    bom = b'\xef\xbb\xbf'

    if data.startswith(bom):
        new_data = (
                bom
                + HEADER.encode("utf-8")
                + b"\r\n"
                + data[len(bom):]
        )
    else:
        new_data = (
                HEADER.encode("utf-8")
                + b"\r\n"
                + data
        )

    output = dst_folder / file.name
    output.write_bytes(new_data)

    print("생성:", output)