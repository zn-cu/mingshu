import {defineConfig} from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
    plugins: [vue()],
    server: {
        proxy: {
            "/api": {
                target: "http://localhost:8000",
                changeOrigin: true,
                configure: (proxy) => {
                    proxy.on("proxyReq", (proxyReq) => {
                        proxyReq.setHeader("Cache-Control", "no-cache");
                        proxyReq.setHeader("Connection", "keep-alive");
                    });
                },
            },
        },
        watch: {
            // 忽略编辑器/工具“原子写入”产生的临时文件与目录。
            // 否则 Windows 上 chokidar 会撞到 EBUSY 并直接让 dev server 退出。
            // Vite 会把这里的规则与内置忽略项（node_modules 等）合并，不会覆盖。
            ignored: [
                "**/.*.tmpdir",
                "**/.*.tmpdir/**",
                "**/*.tmp",
                "**/*.swp",
                "**/*.swx",
                "**/*~",
            ],
        },
    },
});
