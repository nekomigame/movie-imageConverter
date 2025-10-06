import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
from time import sleep
import sys
import subprocess
from PIL import Image
import install_ffmpeg
import threading
from queue import Queue, Empty


class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ファイルコンバーター＆圧縮ツール")
        self.geometry("600x400")

        # --- 変数定義 ---
        self.input_file_path = tk.StringVar()
        self.status_text = tk.StringVar(value="処理するファイルを選択してください。")
        self.mode = tk.StringVar(value="convert")
        self.selected_format = tk.StringVar()
        self.target_size_mb = tk.StringVar(value="10")
        self.selected_encoder = tk.StringVar()
        self.available_encoders = []
        self.ffmpeg_available = False
        self.task_queue = Queue()

        # --- フォーマット定義 ---
        self.image_formats = [
            "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff",
            "ico", "tga", "pcx", "ppm", "pgm", "pbm"
        ]
        self.video_formats = [
            "mp4", "mkv", "mov", "avi", "wmv", "webm", "flv", "mpg",
            "mpeg", "vob", "ogv", "mts", "ts", "m2ts", "3gp", "f4v"
        ]

        # --- FFmpeg and UI setup ---
        self.check_ffmpeg()  # Detect ffmpeg and encoders first
        self.setup_ui()      # Then build the UI

    def check_ffmpeg(self):
        """FFmpegが利用可能か確認し、利用不可の場合は警告を表示する"""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                check=True,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.ffmpeg_available = True
            self.detect_encoders()
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.ffmpeg_available = False
            self.detect_encoders() # Still try to set default
            if messagebox.askokcancel("FFmpegインストール", "FFmpegが見つかりません。FFmpegをインストールしますか？"):
                install_ffmpeg.download_and_extract()
                print("アプリケーションを再起動してください。")
                sleep(10)
                sys.exit()
            else:
                messagebox.showwarning(
                    "FFmpeg Warning",
                    "FFmpegが見つかりません。PCにインストールし、環境変数PATHに登録してください。\n動画の変換・圧縮機能は利用できません。"
                )

    def detect_encoders(self):
        """Detect available H.264 hardware encoders in FFmpeg."""
        self.available_encoders = [("CPU (libx264)", "libx264")]  # Default
        if not self.ffmpeg_available:
            return

        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"],
                capture_output=True, text=True, check=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout
            
            # Check for known H.264 encoders
            if "h264_nvenc" in output:
                self.available_encoders.append(("Nvidia GPU (nvenc)", "h264_nvenc"))
            if "h264_qsv" in output:
                self.available_encoders.append(("Intel GPU (qsv)", "h264_qsv"))
            if "h264_amf" in output:
                self.available_encoders.append(("AMD GPU (amf)", "h264_amf"))

        except (subprocess.CalledProcessError, FileNotFoundError):
            # Silently fail and just use the default CPU encoder.
            pass

    def setup_ui(self):
        # --- ファイル選択フレーム ---
        file_frame = ttk.LabelFrame(self, text="1. ファイル選択", padding=(10, 5))
        file_frame.pack(fill=tk.X, padx=10, pady=5)

        file_entry = ttk.Entry(
            file_frame, textvariable=self.input_file_path, state="readonly", width=60)
        file_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5, pady=5)
        browse_button = ttk.Button(
            file_frame, text="選択...", command=self.select_file)
        browse_button.pack(side=tk.LEFT, padx=5, pady=5)

        # --- モード選択フレーム ---
        mode_frame = ttk.LabelFrame(self, text="2. モード選択", padding=(10, 5))
        mode_frame.pack(fill=tk.X, padx=10, pady=5)

        convert_radio = ttk.Radiobutton(
            mode_frame, text="拡張子変換", variable=self.mode, value="convert", command=self.toggle_mode)
        convert_radio.pack(side=tk.LEFT, padx=10)
        compress_radio = ttk.Radiobutton(
            mode_frame, text="ファイル圧縮", variable=self.mode, value="compress", command=self.toggle_mode)
        compress_radio.pack(side=tk.LEFT, padx=10)

        # --- オプションフレーム ---
        self.options_container = tk.Frame(self)
        self.options_container.pack(fill=tk.X, padx=10, pady=5)

        # 変換オプション
        self.convert_frame = ttk.LabelFrame(
            self.options_container, text="3. 変換オプション", padding=(10, 5))
        format_label = ttk.Label(self.convert_frame, text="変換後フォーマット:")
        format_label.pack(side=tk.LEFT, padx=5)
        self.format_menu = ttk.Combobox(
            self.convert_frame, textvariable=self.selected_format, state="disabled", width=10)
        self.format_menu.pack(side=tk.LEFT, padx=5)

        # 圧縮オプション
        self.compress_frame = ttk.LabelFrame(
            self.options_container, text="3. 圧縮オプション", padding=(10, 5))
        
        size_label = ttk.Label(self.compress_frame, text="目標ファイルサイズ(MB):")
        size_label.pack(side=tk.LEFT, padx=5, pady=5)
        self.size_entry = ttk.Entry(
            self.compress_frame, textvariable=self.target_size_mb, width=10)
        self.size_entry.pack(side=tk.LEFT, padx=5, pady=5)

        encoder_label = ttk.Label(self.compress_frame, text="エンコーダー:")
        encoder_label.pack(side=tk.LEFT, padx=(10, 5), pady=5)
        self.encoder_menu = ttk.Combobox(
            self.compress_frame, textvariable=self.selected_encoder, state="readonly", width=20)
        self.encoder_menu.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.encoder_menu["values"] = [name for name, codec in self.available_encoders]
        if self.encoder_menu["values"]:
            self.selected_encoder.set(self.encoder_menu["values"][0])

        # --- 実行フレーム ---
        execute_frame = tk.Frame(self)
        execute_frame.pack(fill=tk.X, padx=10, pady=10)
        self.execute_button = ttk.Button(
            execute_frame, text="実行", command=self.execute_task, state="disabled")
        self.execute_button.pack(pady=5)

        # --- ステータス表示 ---
        status_label = ttk.Label(
            self, textvariable=self.status_text, foreground="gray", anchor="w")
        status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        self.toggle_mode()  # 初期表示を設定

    def toggle_mode(self):
        mode = self.mode.get()
        if mode == "convert":
            self.compress_frame.pack_forget()
            self.convert_frame.pack(fill=tk.X)
        else:  # compress
            self.convert_frame.pack_forget()
            self.compress_frame.pack(fill=tk.X)

        # ファイルが選択されていればボタンを有効化
        if self.input_file_path.get():
            self.execute_button["state"] = "normal"

    def select_file(self):
        video_ext_str = " ".join([f"*.{ext}" for ext in self.video_formats])
        image_ext_str = " ".join([f"*.{ext}" for ext in self.image_formats])
        filetypes = [
            ("対応ファイル", f"{video_ext_str} {image_ext_str}"), ("すべてのファイル", "*.* ")]

        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if not filepath:
            return

        self.input_file_path.set(filepath)
        self.status_text.set(f"選択中: {os.path.basename(filepath)}")

        self.update_format_options()
        self.toggle_mode()

    def update_format_options(self):
        ext = self.input_file_path.get().split('.')[-1].lower()
        target_formats = []
        if ext in self.image_formats:
            target_formats = [f for f in self.image_formats if f != ext]
        elif ext in self.video_formats:
            target_formats = [f for f in self.video_formats if f != ext]

        self.format_menu["values"] = target_formats
        if target_formats:
            self.selected_format.set(target_formats[0])
            self.format_menu["state"] = "readonly"
        else:
            self.selected_format.set("")
            self.format_menu["state"] = "disabled"
            self.status_text.set("エラー: 対応していないファイル形式です。")

    def execute_task(self):
        if not self.input_file_path.get():
            messagebox.showerror("エラー", "ファイルが選択されていません。")
            return

        self.execute_button["state"] = "disabled"
        self.status_text.set("処理を開始します...")
        
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
            except Empty:
                break

        thread = threading.Thread(target=self._execute_task_threaded)
        thread.daemon = True
        thread.start()
        self.process_queue()

    def _execute_task_threaded(self):
        """This runs in a separate thread."""
        try:
            if self.mode.get() == "convert":
                self.convert_file()
            else:
                self.compress_file()
        except Exception as e:
            self.task_queue.put(("error", e))

    def process_queue(self):
        """Process messages from the worker thread."""
        try:
            message = self.task_queue.get_nowait()
            msg_type, msg_payload = message

            if msg_type == "status":
                self.status_text.set(msg_payload)
            elif msg_type == "error":
                self.status_text.set(f"エラー: {msg_payload}")
                messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{msg_payload}")
                self.execute_button["state"] = "normal"
                return # Stop polling
            elif msg_type == "success":
                mode, msg = msg_payload
                self.status_text.set(f"{mode.capitalize()}完了")
                messagebox.showinfo("成功", msg)
                self.input_file_path.set("")
                self.status_text.set("処理するファイルを選択してください。")
                self.execute_button["state"] = "normal"
                return # Stop polling
            elif msg_type == "warning":
                 messagebox.showwarning("警告", msg_payload)
            
        except Empty:
            pass # No message yet
        
        if self.execute_button["state"] == "disabled":
            self.after(100, self.process_queue)

    def convert_file(self):
        input_path = self.input_file_path.get()
        target_ext = self.selected_format.get()
        if not target_ext:
            raise ValueError("変換後のフォーマットが選択されていません。")

        directory, filename = os.path.split(input_path)
        name_without_ext = os.path.splitext(filename)[0]
        output_path = os.path.join(
            directory, f"{name_without_ext}.{target_ext}")

        self.task_queue.put(("status", f"変換中... -> {os.path.basename(output_path)}"))

        self._run_process(input_path, output_path)
        
        success_msg = f"ファイルの変換が完了しました。\n保存先: {output_path}"
        self.task_queue.put(("success", ("convert", success_msg)))

    def compress_file(self):
        try:
            target_size = float(self.target_size_mb.get())
            if target_size <= 0:
                raise ValueError("目標ファイルサイズは0より大きい値を入力してください。")
        except ValueError:
            raise ValueError("目標ファイルサイズには数値を入力してください。")

        selected_encoder_name = self.selected_encoder.get()
        encoder_codec = "libx264"
        for name, codec in self.available_encoders:
            if name == selected_encoder_name:
                encoder_codec = codec
                break
        
        input_path = self.input_file_path.get()
        directory, filename = os.path.split(input_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(directory, f"{name}_compressed{ext}")

        self.task_queue.put(("status", f"圧縮中... -> {os.path.basename(output_path)}"))

        self._run_process(input_path, output_path, target_size_mb=target_size, encoder=encoder_codec)

        if os.path.exists(output_path):
            final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            self.task_queue.put(("status", f"圧縮完了: {os.path.basename(output_path)} ({final_size_mb:.2f}MB)"))
            success_msg = f"ファイルの圧縮が完了しました。\n保存先: {output_path}"
            self.task_queue.put(("success", ("compress", success_msg)))
        else:
            raise RuntimeError("圧縮ファイルの生成に失敗しました。詳細は警告メッセージを確認してください。")

    def _run_process(self, input_path, output_path, quality=None, target_size_mb=None, encoder=None):
        input_ext = input_path.split('.')[-1].lower()
        if input_ext in self.image_formats:
            self._process_image(input_path, output_path, quality, target_size_mb=target_size_mb)
        elif input_ext in self.video_formats:
            if not self.ffmpeg_available:
                raise RuntimeError("FFmpegが利用できないため、動画処理を実行できません。")
            self._process_video(input_path, output_path, quality, target_size_mb=target_size_mb, encoder=encoder)
        else:
            raise ValueError("対応していないファイル形式です。")

    def _process_image(self, input_path, output_path, quality, target_size_mb=None):
        with Image.open(input_path) as img:
            if target_size_mb is not None:
                target_bytes = target_size_mb * 1024 * 1024
                output_ext = output_path.split('.')[-1].lower()

                if output_ext not in ('jpg', 'jpeg', 'webp'):
                    self.task_queue.put(("warning", f"目標サイズ指定圧縮はJPG/JPEG/WEBP形式でのみ有効です。他の形式ではファイルサイズが変わりません。\nファイルをそのままコピーします。"))
                    img.save(output_path)
                    return

                if output_ext in ('jpg', 'jpeg') and img.mode == 'RGBA':
                    img = img.convert('RGB')

                for q in range(95, 5, -5):
                    try:
                        from io import BytesIO
                        buffer = BytesIO()
                        img_format = 'JPEG' if output_ext in ('jpg', 'jpeg') else output_ext.upper()
                        img.save(buffer, format=img_format, quality=q)
                        if buffer.tell() <= target_bytes:
                            with open(output_path, 'wb') as f:
                                f.write(buffer.getvalue())
                            return
                    except Exception as e:
                        self.task_queue.put(("warning", f".{output_ext} 形式は品質指定による圧縮に失敗しました。\n{e}"))
                        img.save(output_path)
                        return
                
                img.save(output_path, quality=5)
                final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                self.task_queue.put(("warning", f"目標サイズ({target_size_mb:.2f}MB)に到達できませんでした。可能な限り低い品質で圧縮しました (結果: {final_size_mb:.2f}MB)。"))
                return

            options = {}
            output_ext = output_path.split('.')[-1].lower()
            if quality:
                quality_map = {"High": 90, "Medium": 75, "Low": 50}
                options['quality'] = quality_map.get(quality, 75)

            if output_ext in ('jpg', 'jpeg') and img.mode == 'RGBA':
                img = img.convert('RGB')

            img.save(output_path, **options)

    def _get_video_duration(self, input_path):
        """Get video duration in seconds using ffprobe."""
        command = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            input_path
        ]
        try:
            result = subprocess.run(
                command, check=True, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return float(result.stdout.strip())
        except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as e:
            raise RuntimeError(f"動画の長さの取得に失敗しました: {e}\nffprobeがPATHに設定されているか確認してください。")

    def _process_video(self, input_path, output_path, quality, target_size_mb=None, encoder=None):
        if target_size_mb is not None:
            encoder = encoder or "libx264"
            try:
                duration = self._get_video_duration(input_path)
                if duration <= 0:
                    raise RuntimeError("動画の長さが0秒か、取得できませんでした。")
            except Exception as e:
                 raise RuntimeError(f"動画情報の取得に失敗しました:\n{e}")

            audio_bitrate_kbps = 128
            target_total_bitrate_kbps = (target_size_mb * 1024 * 8) / duration
            target_video_bitrate_kbps = target_total_bitrate_kbps - audio_bitrate_kbps

            if target_video_bitrate_kbps <= 100:
                self.task_queue.put(("warning", "目標ファイルサイズが小さすぎるため、品質が著しく低下する可能性があります。"))
                target_video_bitrate_kbps = 100

            target_video_bitrate_str = f"{int(target_video_bitrate_kbps)}k"
            audio_bitrate_str = f"{audio_bitrate_kbps}k"
            
            import tempfile
            with tempfile.TemporaryDirectory() as tempdir:
                log_prefix = os.path.join(tempdir, "ffmpeg2pass")

                self.task_queue.put(("status", f"圧縮中... (1/2 パス, {encoder})"))
                
                pass1_cmd = [
                    "ffmpeg", "-y", "-i", input_path,
                    "-c:v", encoder, "-b:v", target_video_bitrate_str,
                    "-pass", "1", "-passlogfile", log_prefix,
                    "-an", "-f", "mp4", "NUL"
                ]
                
                try:
                    subprocess.run(pass1_cmd, check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(f"FFmpegエラー (パス1, {encoder}):\n{e.stderr}")

                self.task_queue.put(("status", f"圧縮中... (2/2 パス, {encoder})"))

                pass2_cmd = [
                    "ffmpeg", "-i", input_path,
                    "-c:v", encoder, "-b:v", target_video_bitrate_str,
                    "-pass", "2", "-passlogfile", log_prefix,
                    "-c:a", "aac", "-b:a", audio_bitrate_str,
                    "-y", output_path
                ]
                
                try:
                    subprocess.run(pass2_cmd, check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(f"FFmpegエラー (パス2, {encoder}):\n{e.stderr}")
            
            if os.path.exists(output_path):
                final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                if final_size_mb > target_size_mb * 1.1:
                     self.task_queue.put(("warning", f"目標サイズ({target_size_mb:.2f}MB)を少し超えました (結果: {final_size_mb:.2f}MB)。"))
            return

        command = ["ffmpeg", "-i", input_path, "-y"]
        if quality:
            crf_map = {"High": 20, "Medium": 25, "Low": 30}
            command.extend(["-c:v", "libx264", "-crf",
                           str(crf_map.get(quality, 25))])

        command.append(output_path)

        try:
            subprocess.run(command, check=True, capture_output=True,
                           text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except FileNotFoundError:
            raise FileNotFoundError(
                "FFmpegが見つかりません。PCにインストールし、環境変数PATHに登録してください。")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpegエラー:\n{e.stderr}")


if __name__ == "__main__":
    app = ConverterApp()
    app.mainloop()
