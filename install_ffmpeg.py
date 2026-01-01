import urllib.request
import zipfile
import os
import sys
import ssl
import tempfile
import shutil

# Gyan.devから提供されているWindows向けFFmpeg essentialsビルドのURL
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

def get_base_dir():
    """実行環境に応じたベースディレクトリを取得（exe化対応）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def download_and_extract(progress_callback=None):
    """
    FFmpegとFFprobeをダウンロードして、アプリケーションのディレクトリに展開する
    progress_callback: 進捗状況のメッセージ(str)を受け取る関数
    """
    
    def report(msg):
        print(msg)
        if progress_callback:
            progress_callback(msg)

    target_dir = get_base_dir()
    report(f"FFmpegのセットアップを開始します...\nターゲット: {target_dir}")

    # SSL証明書エラー回避
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # 一時ディレクトリを使用してダウンロード（権限エラー回避）
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "ffmpeg_temp.zip")
        
        try:
            report(f"ダウンロード中: {FFMPEG_URL}")
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
                            # 進捗通知（頻度を調整）
                            if bytes_read % (chunk_size * 100) == 0:
                                report(f"ダウンロード中: {bytes_read / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB ({percent:.0f}%)")

            report("ダウンロード完了。解凍してインストール中...")

            extracted_files = []
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.infolist():
                    if member.filename.lower().endswith(('ffmpeg.exe', 'ffprobe.exe')):
                        filename = os.path.basename(member.filename)
                        # binフォルダ内のものか確認
                        if '/bin/' in member.filename.replace('\\', '/'):
                            report(f"  - {filename} を配置中...")
                            target_path = os.path.join(target_dir, filename)
                            
                            # 既存ファイルがある場合は削除してから書き込み
                            if os.path.exists(target_path):
                                try:
                                    os.remove(target_path)
                                except OSError:
                                    report(f"警告: {filename} を上書きできませんでした。使用中の可能性があります。")
                                    continue

                            with open(target_path, "wb") as target_file:
                                target_file.write(zf.read(member))
                            extracted_files.append(filename)

            if len(extracted_files) >= 2:
                report(f"成功: {', '.join(extracted_files)} のセットアップが完了しました。")
            else:
                report("警告: 必要なファイルの一部が見つかりませんでした。")

        except Exception as e:
            report(f"エラーが発生しました: {e}")
            raise e

if __name__ == "__main__":
    download_and_extract()