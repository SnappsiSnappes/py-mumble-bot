1) закинуть mp3 музыку в music
2) в файле .env настроить подключение
3) пуск docker-compose up -d --build
4) команды !list, !play ...
!play можно не до конца писать например 
!play sound
или
!play s


Чтобы сделать так чтобы люди не могли его замутить делаем
1) ```docker-compose up --build -d```
2) выключаем ```docker-compose down```
3) снова включаем ```docker-compose up --build -d```



!speak раз два три --speaker aidar --pitch 32 --rate 12

"""
!speak <текст> — синтез речи через Silero TTS.

Опции:
--speaker <имя>  — голос: xenia, aidar, baya, kseniya, eugene, random
--pitch <0-100>  — высота голоса (50 = норма, >50 = выше)
--rate <0-100>   — скорость речи (50 = норма, >50 = быстрее)

Примеры:
!speak Привет
!speak --speaker aidar Привет от Айдара
!speak --pitch 60 --rate 55 Быстрая высокая речь
!speak --speaker baya --pitch 45 --rate 40 Медленный мягкий голос
"""
