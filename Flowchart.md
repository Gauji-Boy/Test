graph TD
    A[Start Application] --> B{Initialize QApplication};
    B --> C[Create MainWindow Instance];
    C --> D[Show MainWindow];
    D --> E[Start QApplication Event Loop];

    subgraph MainWindow Initialization
        F[MainWindow Constructor] --> F1[Initialize QThreadPool];
        F1 --> F2[Initialize NetworkManager];
        F2 --> F3[Initialize AITools];
        F3 --> F4[Connect AITools Signals to MainWindow Slots];
        F4 --> F5[Setup UI];
        F5 --> F6[Setup Menu];
        F6 --> F7[Setup Toolbar];
        F7 --> F8[Setup Status Bar];
        F8 --> F9[Setup Network Connections];
        F9 --> F10[Load Session];
    end

    C --> F;

    subgraph MainWindow UI Components
        G[Central Widget: QTabWidget (Code Editors)]
        H[Left Dock: FileExplorer]
        I[Bottom Dock: QTabWidget (Terminal)]
        J[Terminal Tab: InteractiveTerminal]
    end

    F5 --> G;
    F5 --> H;
    F5 --> I;
    I --> J;

    subgraph User Interactions
        K[User Action: Open File] --> L[MainWindow.open_file];
        L --> G;
        L --> H;
        H -- file_opened --> L;

        M[User Action: Save File] --> N[MainWindow.save_current_file];
        N --> G;

        O[User Action: Run Code] --> P[MainWindow._handle_run_request];
        P --> N;
        P --> J;
        P --> Q[QProcess (Code Execution)];
        Q -- stdout/stderr --> J;

        R[User Action: Start Hosting Session] --> S[MainWindow.start_hosting_session];
        S --> T[NetworkManager.start_hosting];

        U[User Action: Connect to Host] --> V[MainWindow.connect_to_host_session];
        V --> W[NetworkManager.connect_to_host];

        X[User Action: Request Control] --> Y[MainWindow.request_control];
        Y --> Z[NetworkManager.send_data (CONTROL_REQUEST)];

        AA[User Action: Open AI Assistant] --> BB[MainWindow.open_ai_assistant];
        BB --> CC[AIAssistantWindow];
        CC --> DD[AITools];
        DD -- signals --> F4;
    end

    subgraph Collaborative Editing Flow
        E1[NetworkManager.data_received] --> E2[MainWindow.on_network_data_received];
        E2 --> G;
        E3[MainWindow.on_text_editor_changed] -- if has_control --> E4[NetworkManager.send_data (TEXT_UPDATE)];
        E4 --> E1;
    end

    subgraph Control Management Flow
        F11[NetworkManager.control_request_received] --> F12[MainWindow.on_control_request_received];
        F12 --> F13{Host Grants/Declines?};
        F13 -- Grant --> F14[NetworkManager.send_data (CONTROL_GRANTED)];
        F13 -- Decline --> F15[NetworkManager.send_data (CONTROL_DECLINED)];
        F14 --> F16[MainWindow.on_control_granted];
        F15 --> F17[MainWindow.on_control_declined];
        F16 --> F18[Update UI for Control State];
        F17 --> F18;
        F19[NetworkManager.control_revoked] --> F20[MainWindow.on_control_revoked];
        F20 --> F18;
    end

    F9 --> E1;
    F9 --> F11;
    F9 --> F19;
    G --> E3;
