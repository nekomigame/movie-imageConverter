import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import sys
import subprocess
from PIL import Image
import install_ffmpeg
import threading
from queue import Queue, Empty
import shutil
import tempfile
import traceback
import json

class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ファイルコンバーター＆圧縮ツール")
        self.geometry("650x550")

        # ウィンドウを閉じる時のイベントをフック
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- 変数定義 ---
        self.input_file_path = tk.StringVar()
        self.status_text = tk.StringVar(value="処理するファイルを選択してください。")
        self.mode = tk.StringVar(value="convert")
        self.selected_format = tk.StringVar()
        self.target_size_mb = tk.StringVar(value="10")
        self.selected_encoder = tk.StringVar()
        self.quality_var = tk.StringVar(value="Medium") # 画質選択用
        self.available_encoders = []
        self.task_queue = Queue()
        self.worker_thread = None
        self.current_process = None
        self.cancel_requested = False
        
        # FFmpeg/FFprobeのパス
        self.ffmpeg_path = None
        self.ffprobe_path = None

        # --- フォーマット定義 ---
        # Pillowで処理する画像形式
        self.image_formats = [
            "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff",
            "ico", "tga", "ppm"
        ]
        
        # FFmpegで処理する形式 (動画のみ)
        self.video_formats = [
            # 一般的な動画
            "mp4", "mkv", "mov", "avi", "wmv", "webm", "flv", "mpg", "mpeg", 
            "ts", "m2ts", "3gp", "3g2", "m4v", "vob", "ogv", "mts", "mxf",
            "rm", "rmvb", "asf", "amv", "divx", "f4v", "m2v", "mpe", "mpv", 
            "mpeg1", "mpeg2", "mpeg4", "ogm", "ogx", "dv", "drc", "gvi", 
            "iso", "m1v", "tod", "vro", "wtv", "xesc", "bin", "nsv", "nuv", "rec"
        ]

        # --- 初期化プロセス ---
        self.locate_binaries() # FFmpegのパスを解決
        self.setup_ui()        # UI構築
        
        # UI構築後にエンコーダー検出を行う
        if self.ffmpeg_path:
            self.detect_encoders()
        else:
            self.after(500, self.check_and_install_ffmpeg)

    def on_closing(self):
        """アプリ終了時のクリーンアップ処理"""
        if self.worker_thread and self.worker_thread.is_alive():
            if messagebox.askokcancel("終了確認", "処理が実行中です。強制終了しますか？"):
                self.cancel_task()
                self.destroy()
        else:
            self.destroy()

    def locate_binaries(self):
        """ローカルディレクトリ、またはPATHからFFmpeg/FFprobeを探す"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        local_ffmpeg = os.path.join(current_dir, "ffmpeg.exe")
        local_ffprobe = os.path.join(current_dir, "ffprobe.exe")
        
        # 優先順位: カレントディレクトリ > PATH
        if os.path.exists(local_ffmpeg):
            self.ffmpeg_path = local_ffmpeg
        else:
            self.ffmpeg_path = shutil.which("ffmpeg")

        if os.path.exists(local_ffprobe):
            self.ffprobe_path = local_ffprobe
        else:
            self.ffprobe_path = shutil.which("ffprobe")

    def check_and_install_ffmpeg(self):
        if not self.ffmpeg_path:
            self.available_encoders = [("CPU (libx264)", "libx264")]
            if messagebox.askyesno("FFmpeg不足", "動画処理に必要なFFmpegが見つかりません。\n自動的にダウンロードしてインストールしますか？"):
                self.status_text.set("FFmpegをダウンロード中...")
                self.execute_button["state"] = "disabled"
                
                # ダウンロードを別スレッドで実行
                threading.Thread(target=self._download_ffmpeg_thread, daemon=True).start()
            else:
                self.status_text.set("警告: FFmpegがないため、動画機能は制限されます。")

    def _download_ffmpeg_thread(self):
        try:
            # 進捗表示用のコールバック
            def progress_callback(msg):
                self.task_queue.put(("status", msg))

            install_ffmpeg.download_and_extract(progress_callback=progress_callback)
            
            # メインスレッドで再検出を実行させる
            self.task_queue.put(("ffmpeg_installed", None))
            
        except Exception as e:
            self.task_queue.put(("error", f"ダウンロードエラー: {e}"))

    def detect_encoders(self):
        """利用可能なH.264ハードウェアエンコーダーを検出し、メニューを更新する"""
        self.available_encoders = [("CPU (libx264)", "libx264")]
        
        if self.ffmpeg_path:
            try:
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                result = subprocess.run(
                    [self.ffmpeg_path, "-encoders"],
                    capture_output=True, text=True, check=True,
                    startupinfo=startupinfo
                )
                output = result.stdout
                
                if "h264_nvenc" in output:
                    self.available_encoders.append(("Nvidia GPU (nvenc)", "h264_nvenc"))
                if "h264_qsv" in output:
                    self.available_encoders.append(("Intel GPU (qsv)", "h264_qsv"))
                if "h264_amf" in output:
                    self.available_encoders.append(("AMD GPU (amf)", "h264_amf"))

            except Exception:
                pass 

        self.update_encoder_menu()

    def update_encoder_menu(self):
        """検出されたエンコーダーをドロップダウンリストに反映させる"""
        # メニュー項目
        menu_values = [name for name, codec in self.available_encoders]
        
        # 圧縮用メニュー更新
        if hasattr(self, 'encoder_menu'):
            self.encoder_menu["values"] = menu_values
        
        # 変換用メニュー更新
        if hasattr(self, 'convert_encoder_menu'):
            self.convert_encoder_menu["values"] = menu_values

        # 初期選択
        if menu_values:
            self.selected_encoder.set(menu_values[0])

    def setup_ui(self):
        # --- ファイル選択 ---
        file_frame = ttk.LabelFrame(self, text="1. ファイル選択", padding=(10, 5))
        file_frame.pack(fill=tk.X, padx=10, pady=5)

        file_entry = ttk.Entry(
            file_frame, textvariable=self.input_file_path, state="readonly", width=60)
        file_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5, pady=5)
        browse_button = ttk.Button(
            file_frame, text="選択...", command=self.select_file)
        browse_button.pack(side=tk.LEFT, padx=5, pady=5)

        # --- モード選択 ---
        mode_frame = ttk.LabelFrame(self, text="2. モード選択", padding=(10, 5))
        mode_frame.pack(fill=tk.X, padx=10, pady=5)

        convert_radio = ttk.Radiobutton(
            mode_frame, text="拡張子変換 / 画質変更", variable=self.mode, value="convert", command=self.toggle_mode)
        convert_radio.pack(side=tk.LEFT, padx=10)
        compress_radio = ttk.Radiobutton(
            mode_frame, text="目標サイズで圧縮", variable=self.mode, value="compress", command=self.toggle_mode)
        compress_radio.pack(side=tk.LEFT, padx=10)

        # --- オプション ---
        self.options_container = tk.Frame(self)
        self.options_container.pack(fill=tk.X, padx=10, pady=5)

        # 変換オプション（通常モード）
        self.convert_frame = ttk.LabelFrame(
            self.options_container, text="3. 変換設定", padding=(10, 5))
        
        # 1行目: 形式と画質
        row1 = tk.Frame(self.convert_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="変換後形式:").pack(side=tk.LEFT, padx=5)
        self.format_menu = ttk.Combobox(
            row1, textvariable=self.selected_format, state="disabled", width=10)
        self.format_menu.pack(side=tk.LEFT, padx=5)

        ttk.Label(row1, text="画質:").pack(side=tk.LEFT, padx=(15, 5))
        quality_menu = ttk.Combobox(
            row1, textvariable=self.quality_var, 
            values=["Original", "High", "Medium", "Low"], state="readonly", width=10)
        quality_menu.pack(side=tk.LEFT, padx=5)

        # 2行目: エンコーダー選択
        row2 = tk.Frame(self.convert_frame)
        row2.pack(fill=tk.X, pady=5)
        ttk.Label(row2, text="エンコーダー(動画):").pack(side=tk.LEFT, padx=5)
        self.convert_encoder_menu = ttk.Combobox(
            row2, textvariable=self.selected_encoder, state="readonly", width=30)
        self.convert_encoder_menu.pack(side=tk.LEFT, padx=5)


        # 圧縮オプション（サイズ指定モード）
        self.compress_frame = ttk.LabelFrame(
            self.options_container, text="3. 圧縮設定 (2パスエンコード)", padding=(10, 5))
        
        size_label = ttk.Label(self.compress_frame, text="目標ファイルサイズ(MB):")
        size_label.pack(side=tk.LEFT, padx=5, pady=5)
        self.size_entry = ttk.Entry(
            self.compress_frame, textvariable=self.target_size_mb, width=10)
        self.size_entry.pack(side=tk.LEFT, padx=5, pady=5)

        encoder_label = ttk.Label(self.compress_frame, text="エンコーダー(動画のみ):")
        encoder_label.pack(side=tk.LEFT, padx=(10, 5), pady=5)
        self.encoder_menu = ttk.Combobox(
            self.compress_frame, textvariable=self.selected_encoder, state="readonly", width=30)
        self.encoder_menu.pack(side=tk.LEFT, padx=5, pady=5)
        
        # --- 実行エリア ---
        execute_frame = tk.Frame(self)
        execute_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.progressbar = ttk.Progressbar(execute_frame, mode='indeterminate')
        self.progressbar.pack(fill=tk.X, padx=5, pady=(0, 10))

        btn_frame = tk.Frame(execute_frame)
        btn_frame.pack(fill=tk.X)

        self.execute_button = ttk.Button(
            btn_frame, text="実行", command=self.execute_task, state="disabled")
        self.execute_button.pack(side=tk.LEFT, padx=5, pady=5, expand=True, fill=tk.X)

        self.cancel_button = ttk.Button(
            btn_frame, text="中止", command=self.cancel_task, state="disabled")
        self.cancel_button.pack(side=tk.LEFT, padx=5, pady=5, expand=True, fill=tk.X)

        # --- ステータス ---
        status_label = ttk.Label(
            self, textvariable=self.status_text, foreground="#333333", anchor="w", relief="sunken")
        status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=0, pady=0, ipady=3)

        self.toggle_mode()
        self.update_encoder_menu()
        self.process_queue()

    def toggle_mode(self):
        mode = self.mode.get()
        if mode == "convert":
            self.compress_frame.pack_forget()
            self.convert_frame.pack(fill=tk.X)
        else:
            self.convert_frame.pack_forget()
            self.compress_frame.pack(fill=tk.X)

        if self.input_file_path.get():
            self.execute_button["state"] = "normal"

    def select_file(self):
        media_exts = []
        media_exts.extend([f"*.{ext}" for ext in self.video_formats])
        media_exts.extend([f"*.{ext}" for ext in self.image_formats])
        
        filetypes = [
            ("メディアファイル", " ".join(media_exts)),
            ("動画ファイル", " ".join([f"*.{ext}" for ext in self.video_formats])),
            ("画像ファイル", " ".join([f"*.{ext}" for ext in self.image_formats])),
            ("すべてのファイル", "*.*")
        ]

        try:
            filepath = filedialog.askopenfilename(filetypes=filetypes)
        except Exception:
            filepath = filedialog.askopenfilename(filetypes=[("すべてのファイル", "*.*")])

        if not filepath: return

        self.input_file_path.set(filepath)
        self.status_text.set(f"選択中: {os.path.basename(filepath)}")
        self.update_format_options()
        self.toggle_mode()

    def update_format_options(self):
        ext = self.input_file_path.get().split('.')[-1].lower()
        target_formats = []
        
        if ext in self.image_formats:
            target_formats = [f for f in self.image_formats]
        else:
            common_outputs = [
                "mp4", "mkv", "mov", "avi", "webm", "flv", "gif"
            ]
            target_formats = [f for f in common_outputs]
            # 現在の拡張子がリストにない場合は追加する
            if ext not in target_formats:
                target_formats.append(ext)

        self.format_menu["values"] = target_formats
        self.format_menu["state"] = "normal"
        
        # デフォルトで現在の拡張子を選択状態にする
        self.selected_format.set(ext)

    def execute_task(self):
        if not self.input_file_path.get():
            messagebox.showerror("エラー", "ファイルが選択されていません。")
            return

        params = {
            "mode": self.mode.get(),
            "input_path": self.input_file_path.get(),
            "target_ext": self.selected_format.get(),
            "target_size_mb": self.target_size_mb.get(),
            "selected_encoder": self.selected_encoder.get(),
            "quality": self.quality_var.get()
        }

        self.execute_button["state"] = "disabled"
        self.cancel_button["state"] = "normal"
        self.progressbar.start(10)
        self.status_text.set("処理を開始します...")
        self.cancel_requested = False
        
        while not self.task_queue.empty():
            try: self.task_queue.get_nowait()
            except Empty: break

        self.worker_thread = threading.Thread(target=self._execute_task_threaded, args=(params,))
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def cancel_task(self):
        if self.worker_thread and self.worker_thread.is_alive():
            if messagebox.askokcancel("確認", "処理を中止しますか？"):
                self.cancel_requested = True
                self.status_text.set("中止処理中...")
                if self.current_process:
                    try:
                        self.current_process.kill()
                    except Exception:
                        pass
        else:
            self.cancel_button["state"] = "disabled"

    def _execute_task_threaded(self, params):
        try:
            if params["mode"] == "convert":
                self.convert_file(params)
            else:
                self.compress_file(params)
        except Exception as e:
            traceback.print_exc()
            if not self.cancel_requested:
                self.task_queue.put(("error", str(e)))

    def _reset_ui_after_task(self, status_message, success=False):
        self.status_text.set(status_message)
        self.progressbar.stop()
        self.execute_button["state"] = "normal"
        self.cancel_button["state"] = "disabled"
        self.current_process = None
        self.cancel_requested = False
        if success:
            self.input_file_path.set("")
            
    def process_queue(self):
        try:
            while True:
                message = self.task_queue.get_nowait()
                msg_type, msg_payload = message

                if msg_type == "status":
                    self.status_text.set(msg_payload)
                    
                elif msg_type == "ffmpeg_installed":
                    self.locate_binaries()
                    self.detect_encoders()
                    self.status_text.set("FFmpegのインストールが完了しました。")
                    self.execute_button["state"] = "normal"
                    messagebox.showinfo("完了", "FFmpegの準備が完了しました。")

                elif msg_type == "error":
                    self._reset_ui_after_task("エラーが発生しました", success=False)
                    messagebox.showerror("処理エラー", msg_payload)
                    
                elif msg_type == "success":
                    mode, msg = msg_payload
                    self._reset_ui_after_task(f"{mode}完了", success=True)
                    messagebox.showinfo("処理終了", msg)
                    
                elif msg_type == "cancelled":
                    self._reset_ui_after_task("処理が中断されました。", success=False)
                    messagebox.showwarning("中止", "処理がユーザーによって中断されました。")
                    
                elif msg_type == "warning":
                     messagebox.showwarning("警告", msg_payload)
        
        except Empty:
            pass
        
        self.after(100, self.process_queue)

    def convert_file(self, params):
        input_path = params["input_path"]
        target_ext = params["target_ext"]
        quality = params["quality"]
        # メニュー表示名からコーデック名を取得
        selected_encoder_name = params.get("selected_encoder")
        encoder_codec = "libx264" # デフォルト
        for name, codec in self.available_encoders:
            if name == selected_encoder_name:
                encoder_codec = codec
                break
        
        if not target_ext:
            target_ext = input_path.split('.')[-1]

        directory, filename = os.path.split(input_path)
        name_without_ext = os.path.splitext(filename)[0]
        output_path = os.path.join(directory, f"{name_without_ext}_converted.{target_ext}")

        if os.path.abspath(input_path) == os.path.abspath(output_path):
             output_path = os.path.join(directory, f"{name_without_ext}_new.{target_ext}")

        self.task_queue.put(("status", f"変換中({quality}, {encoder_codec})... -> {os.path.basename(output_path)}"))
        self._run_process(input_path, output_path, quality=quality, encoder=encoder_codec)
        
        if not self.cancel_requested:
            success_msg = f"ファイルの変換が完了しました。\n保存先: {output_path}"
            self.task_queue.put(("success", ("変換", success_msg)))
        else:
            self.task_queue.put(("cancelled", None))

    def compress_file(self, params):
        try:
            target_size = float(params["target_size_mb"])
            if target_size <= 0: raise ValueError
        except ValueError:
            raise ValueError("目標ファイルサイズには正しい数値を入力してください。")

        selected_encoder_name = params["selected_encoder"]
        encoder_codec = "libx264"
        for name, codec in self.available_encoders:
            if name == selected_encoder_name:
                encoder_codec = codec
                break
        
        input_path = params["input_path"]
        directory, filename = os.path.split(input_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(directory, f"{name}_compressed{ext}")
        
        if os.path.abspath(input_path) == os.path.abspath(output_path):
             output_path = os.path.join(directory, f"{name}_compressed_new{ext}")

        self.task_queue.put(("status", f"圧縮中... -> {os.path.basename(output_path)}"))
        
        self._run_process(input_path, output_path, target_size_mb=target_size, encoder=encoder_codec)

        if self.cancel_requested:
            self.task_queue.put(("cancelled", None))
            if os.path.exists(output_path):
                try: os.remove(output_path)
                except: pass
            return

        if os.path.exists(output_path):
            final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            msg = f"圧縮完了: {os.path.basename(output_path)} ({final_size_mb:.2f}MB)"
            self.task_queue.put(("status", msg))
            success_msg = f"ファイルの圧縮が完了しました。\n保存先: {output_path}\nサイズ: {final_size_mb:.2f}MB"
            self.task_queue.put(("success", ("圧縮", success_msg)))
        else:
            raise RuntimeError("出力ファイルが生成されませんでした。")

    def _run_process(self, input_path, output_path, quality=None, target_size_mb=None, encoder=None):
        input_ext = input_path.split('.')[-1].lower()
        
        if input_ext in self.image_formats:
            self._process_image(input_path, output_path, quality, target_size_mb=target_size_mb)
        else:
            if not self.ffmpeg_path:
                raise RuntimeError("FFmpegが見つからないため、処理を実行できません。")
            self._process_video(input_path, output_path, quality, target_size_mb=target_size_mb, encoder=encoder)

    def _process_image(self, input_path, output_path, quality, target_size_mb=None):
        with Image.open(input_path) as img:
            output_ext = output_path.split('.')[-1].lower()
            
            if output_ext in ('jpg', 'jpeg') and img.mode in ('RGBA', 'LA'):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif output_ext in ('jpg', 'jpeg') and img.mode == 'P':
                 img = img.convert('RGB')

            if target_size_mb is not None:
                target_bytes = target_size_mb * 1024 * 1024

                if output_ext not in ('jpg', 'jpeg', 'webp'):
                    self.task_queue.put(("warning", f"目標サイズ圧縮はJPG/WebPのみ対応しています。通常の変換を行います。"))
                    img.save(output_path)
                    return

                low, high = 1, 95
                best_quality = 5
                
                from io import BytesIO
                
                buffer = BytesIO()
                img_format = 'JPEG' if output_ext in ('jpg', 'jpeg') else output_ext.upper()
                img.save(buffer, format=img_format, quality=high)
                if buffer.tell() <= target_bytes:
                    with open(output_path, 'wb') as f:
                        f.write(buffer.getvalue())
                    return

                while low <= high:
                    if self.cancel_requested: return
                    mid = (low + high) // 2
                    buffer = BytesIO()
                    img.save(buffer, format=img_format, quality=mid)
                    size = buffer.tell()
                    
                    if size <= target_bytes:
                        best_quality = mid
                        low = mid + 1
                    else:
                        high = mid - 1
                
                img.save(output_path, quality=best_quality)
                
                final_size = os.path.getsize(output_path)
                if final_size > target_bytes:
                     self.task_queue.put(("warning", f"最低画質でも目標サイズを超過しました ({final_size/(1024*1024):.2f}MB)。"))
                return

            options = {}
            if quality == "Original":
                if output_ext in ('jpg', 'jpeg'):
                    options['quality'] = 100
                    options['subsampling'] = 0
                elif output_ext == 'webp':
                    options['quality'] = 100
                    options['lossless'] = True
            elif output_ext in ('jpg', 'jpeg', 'webp'):
                q_val = {"High": 90, "Medium": 75, "Low": 50}.get(quality, 75)
                options['quality'] = q_val
            
            img.save(output_path, **options)

    def _get_video_duration(self, input_path):
        if not self.ffprobe_path: raise RuntimeError("ffprobeが見つかりません。")
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        command = [
            self.ffprobe_path, "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ]
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, startupinfo=startupinfo
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            raise RuntimeError("動画の長さを取得できませんでした。")

    def _has_audio_stream(self, input_path):
        """動画ファイルに音声ストリームがあるか確認する"""
        if not self.ffprobe_path: return False
        
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        command = [
            self.ffprobe_path, "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0", input_path
        ]
        
        try:
            result = subprocess.run(
                command, check=False, capture_output=True, text=True, startupinfo=startupinfo
            )
            # 出力があれば音声ストリームが存在する
            return bool(result.stdout.strip())
        except Exception:
            # エラーの場合は安全のため音声なしとみなすか、ありとみなすか。
            # ここでは処理続行のためFalseを返す
            return False

    def _process_video(self, input_path, output_path, quality, target_size_mb=None, encoder=None):
        if self.cancel_requested: return
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # 音声ストリームの有無を確認
        has_audio = self._has_audio_stream(input_path)

        # --- 目標サイズ指定（2パスエンコード） ---
        if target_size_mb is not None:
            encoder = encoder or "libx264"
            try:
                duration = self._get_video_duration(input_path)
            except Exception as e:
                 raise RuntimeError(f"動画情報の取得失敗: {e}")

            # ビットレート計算
            audio_bitrate_kbps = 128 if has_audio else 0
            target_total_bitrate_kbps = (target_size_mb * 1024 * 8) / duration
            target_video_bitrate_kbps = target_total_bitrate_kbps - audio_bitrate_kbps

            if target_video_bitrate_kbps < 50:
                self.task_queue.put(("warning", "目標サイズが極端に小さいため、画質が大幅に低下します。"))
                target_video_bitrate_kbps = max(30, target_video_bitrate_kbps)

            target_video_bitrate_str = f"{int(target_video_bitrate_kbps)}k"
            audio_bitrate_str = f"{audio_bitrate_kbps}k"
            
            with tempfile.TemporaryDirectory() as tempdir:
                log_prefix = os.path.join(tempdir, "ffmpeg2pass").replace('\\', '/')
                null_device = "NUL" if os.name == 'nt' else "/dev/null"

                self.task_queue.put(("status", f"圧縮中... (1/2 パス, {encoder})"))
                
                pass1_cmd = [
                    self.ffmpeg_path, "-y", "-i", input_path,
                    "-c:v", encoder, "-b:v", target_video_bitrate_str,
                    "-pass", "1", "-passlogfile", log_prefix,
                    "-an", # Pass1は必ず音声なし
                    "-f", "mp4", null_device
                ]
                
                self.current_process = subprocess.Popen(
                    pass1_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                    text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo
                )
                _, stderr = self.current_process.communicate()
                
                if self.current_process.returncode != 0 and not self.cancel_requested:
                     raise RuntimeError(f"FFmpeg Pass1 エラー:\n{stderr}")
                
                if self.cancel_requested: return

                self.task_queue.put(("status", f"圧縮中... (2/2 パス, {encoder})"))

                pass2_cmd = [
                    self.ffmpeg_path, "-i", input_path,
                    "-c:v", encoder, "-b:v", target_video_bitrate_str,
                    "-pass", "2", "-passlogfile", log_prefix,
                ]

                # 音声設定の追加
                if has_audio:
                    pass2_cmd.extend(["-c:a", "aac", "-b:a", audio_bitrate_str])
                else:
                    pass2_cmd.append("-an")

                pass2_cmd.extend(["-y", output_path])
                
                self.current_process = subprocess.Popen(
                    pass2_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                    text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo
                )
                _, stderr = self.current_process.communicate()
                
                if self.current_process.returncode != 0 and not self.cancel_requested:
                    raise RuntimeError(f"FFmpeg Pass2 エラー:\n{stderr}")
            return

        # --- 通常変換モード (拡張子変換 / 画質設定) ---
        output_ext = output_path.split('.')[-1].lower()
        
        # Original (ストリームコピー) モード
        # まずストリームコピーを試みる。失敗したら再エンコードにフォールバック
        need_reencode = True
        
        if quality == "Original":
             command = [
                self.ffmpeg_path, "-i", input_path,
                "-c", "copy",
                "-y", output_path
            ]
             
             self.current_process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo
            )
             _, stderr = self.current_process.communicate()
             
             if self.current_process.returncode == 0:
                 need_reencode = False # 成功したので終了
             elif self.cancel_requested:
                 return # キャンセル時は何もしない
             else:
                 # 失敗した場合
                 self.task_queue.put(("warning", "ストリームコピー不可のため、自動的に再エンコードします。"))
                 quality = "High"
                 encoder = encoder or "libx264"
                 need_reencode = True
        else:
             need_reencode = True

        if not need_reencode:
            return
            
        # 主要動画形式で再エンコードする場合
        # ハードウェアエンコード(H.264)が格納可能なコンテナを網羅する
        supported_x264_containers = [
            "mp4", "mkv", "mov", "avi", "flv", "ts", "m2ts", "3gp", "wmv",
            "m4v", "mts", "f4v", "3g2"
        ]

        if output_ext in supported_x264_containers:
            encoder = encoder or "libx264"
            
            command = [
                self.ffmpeg_path, "-i", input_path,
                "-c:v", encoder,
            ]
            
            # エンコーダーごとの画質制御
            if encoder == "libx264":
                # CRF (Constant Rate Factor)
                crf_val = "23"
                if quality == "High": crf_val = "18"
                elif quality == "Low": crf_val = "28"
                command.extend(["-crf", crf_val, "-preset", "medium"])
                
            elif encoder == "h264_nvenc":
                # Nvidia NVENC
                cq_val = "23"
                if quality == "High": cq_val = "19"
                elif quality == "Low": cq_val = "28"
                command.extend(["-rc:v", "vbr_hq", "-cq:v", cq_val, "-b:v", "0"])
                
            elif encoder == "h264_qsv":
                # Intel QSV
                q_val = "25"
                if quality == "High": q_val = "20"
                elif quality == "Low": q_val = "30"
                command.extend(["-global_quality", q_val])
            
            else:
                pass

            # 音声設定
            if has_audio:
                command.extend(["-c:a", "aac"])
            else:
                command.append("-an")

            command.extend(["-y", output_path])
            
        else:
            # その他の形式（WebM, GIFなど H.264 コーデックが使えない形式）
            # 標準変換（CPU）を行う
            if quality != "Original":
                self.task_queue.put(("status", f"変換中... (形式 {output_ext} は選択されたHWエンコード未対応のため標準変換)"))

            command = [
                self.ffmpeg_path, "-i", input_path,
                "-y", output_path
            ]
        
        self.current_process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
            text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo
        )
        _, stderr = self.current_process.communicate()
        
        if self.current_process.returncode != 0 and not self.cancel_requested:
            raise RuntimeError(f"FFmpeg エラー:\n{stderr}")

if __name__ == "__main__":
    app = ConverterApp()
    app.mainloop()