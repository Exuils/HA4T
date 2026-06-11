# HA4T Editor

> 鸣谢 [codematrixer/ui-viewer](https://github.com/codematrixer/ui-viewer) (MIT)

UI hierarchy inspector for Mobile App, supporting `Android`, `iOS`, and `HarmonyOS NEXT`. 

Its features include:

- visualize the UI hierarchy via screenshot and tree structure.
- view element properties
- auto generate XPath or XPathLite
- auto generate coordinate percentages.
- and more…


This project is developed using FastAPI + Vue 3 + Element Plus. It starts locally and displays UI hierarchy through web browser.

![show](https://github.com/user-attachments/assets/cd277443-2064-4c98-a5c9-214ee6fae674)

# Installation
- python3.8+
```shell
pip install -e .
```

# Run
Run the following command on the terminal. (default port `8000`)

```shell
python -m ha4t.editor [-p PORT]
```

And then open the browser to [http://localhost:8000](http://localhost:8000)

You can also customize port to start the service.
```shell
python -m ha4t.editor -p <PORT>
```

# Environment
If you need to connect to a remote HDC Server or ADB server for remote device debugging, you must set the required environment variables before starting uiviewer.

HarmonyOS
```bash
export HDC_SERVER_HOST=127.0.0.1  # Replace with the remote host
export HDC_SERVER_PORT=8710
```

Android
```bash
export ANDROID_ADB_SERVER_HOST=127.0.0.1  # Replace with the remote host
export ANDROID_ADB_SERVER_PORT=5037
```

If you want to remove Environment Variables, To unset the environment variables:
```bash
unset HDC_SERVER_HOST
unset HDC_SERVER_PORT

unset ANDROID_ADB_SERVER_HOST
unset ANDROID_ADB_SERVER_PORT
```


# Tips
- If you are using a virtual environment, please make sure to activate it before running the command.

- On iOS, please ensure that WDA is successfully started and wda port forwarding is successful in advance.
  -   First, Use `xcode` or  `tidevice` or `go-ios` to launch wda.
  ```
  tidevice xctest -B <wda_bundle_id>
  ```
  - Second, Use `tidevice` or `iproxy` to forward the wda port，and keep it running.
  ```
  tidevice relay 8100 8100
  ```
  - And then, To ensure the success of the browser to access `http://localhost:8100/status`, return like this:
  ```
  {
    "value": {
        "build": {
            "productBundleIdentifier": "com.facebook.WebDriverAgentRunner",
            "time": "Mar 25 2024 15:17:30"
        },
        ...
        "state": "success",
        "ready": true
    },
    "sessionId": null
  } 
  ```
  - Finally, Input the **`wdaUrl`** in the web page, such as `http://localhost:8100`

- On iOS，WDA can easily freeze when dumping high UI hierarchy. You can reduce the **`maxDepth`** on the web page. The default is 30.


# Relevant
- https://github.com/codematrixer/hmdriver2
- https://github.com/openatx/uiautomator2
- https://github.com/openatx/facebook-wda
- https://github.com/alibaba/web-editor
