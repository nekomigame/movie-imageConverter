# 動作確認済み環境  
<table>
  <tr>
    <th>os</th>
    <th>language</th>
  </tr>
  <tr>
    <th>Windows 10</th>
    <th>Python 3(3.11.3)</th>
  </tr>
</table>

# 実行手順  

```
git clone https://github.com/nekomigame/movie-imageConverter.git
python venv venv
./venv/scripts/activate
pip install -r requirements.txt
python main.py
```

# FFmpegについて
このプログラムはFFmpegを用いて処理を行っているためFFmpegが必要です。  
インストールされていない場合は自動でインストールされます。
