import urllib.request
import zipfile
import os
import sys
import ssl

# Gyan.devから提供されているWindows向けFFmpeg essentialsビルドのURL
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

def download_and_extract(progress_callback=None):
    """
    FFmpegとFFprobeをダウンロードして、カレントディレクトリに展開する
    progress_callback: 進捗状況のメッセージ(str)を受け取る関数
    """
    
    def report(msg):
        print(msg)
        if progress_callback:
            progress_callback(msg)

    target_dir = os.path.dirname(os.path.abspath(__file__)) # スクリプトのある場所を基準にする
    report(f"FFmpegのダウンロードを開始します...\nURL: {FFMPEG_URL}")

    # SSL証明書エラー回避（環境によっては必要）
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # User-Agentを設定しないと403エラーになる場合があるためヘッダーを追加
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    zip_path = os.path.join(target_dir, "ffmpeg_temp.zip")

    try:
        req = urllib.request.Request(FFMPEG_URL, headers=headers)
        with urllib.request.urlopen(req, context=ctx) as response:
            if response.status != 200:
                raise Exception(f"ダウンロード失敗 (Status: {response.status})")

            total_size = int(response.headers.get('content-length', 0))
            chunk_size = 8192
            bytes_read = 0

            with open(zip_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_read += len(chunk)
                    
                    if total_size > 0:
                        percent = (bytes_read / total_size) * 100
                        # 10%ごとに通知、またはMB単位で通知
                        if bytes_read % (chunk_size * 50) == 0:
                            report(f"ダウンロード中: {bytes_read / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB ({percent:.0f}%)")

            report("ダウンロード完了。解凍中...")

        extracted_files = []
        with zipfile.ZipFile(zip_path) as zf:
            # ファイルリストを取得して、ffmpeg.exe/ffprobe.exeを探す
            for member in zf.infolist():
                # binフォルダ内のexeファイルを探す (アーカイブ内のパス構造に依存しないように検索)
                if member.filename.lower().endswith(('ffmpeg.exe', 'ffprobe.exe')):
                    filename = os.path.basename(member.filename)
                    # binフォルダに入っているものだけを対象とする（念のため）
                    if '/bin/' in member.filename.replace('\\', '/'):
                        report(f"  - {filename} を展開中...")
                        target_path = os.path.join(target_dir, filename)
                        
                        with open(target_path, "wb") as target_file:
                            target_file.write(zf.read(member))
                        extracted_files.append(filename)

        if len(extracted_files) >= 2:
            report(f"成功: {', '.join(extracted_files)} のセットアップが完了しました。")
        else:
            report("警告: 必要なファイルの一部が見つかりませんでした。")

    except Exception as e:
        report(f"エラーが発生しました: {e}")
        raise e # 呼び出し元にエラーを伝播
    finally:
        # 一時ファイルの削除
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except:
                pass

if __name__ == "__main__":
    download_and_extract()