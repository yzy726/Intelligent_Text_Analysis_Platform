
/**
 * 质构文析台 - PC端主逻辑脚本
 * 负责处理页面交互、文件上传、调用后端 API (OCR、信息提取、PDF生成) 以及结果的可视化展示。
 */

// ==================== 全局状态变量 ====================
let fieldList = []; // 存储用户配置的提取字段列表 (包含名称、类型、正则等)
let currentFile = null; // 当前用户上传的文件对象 (File)
let currentFileUrl = ''; // 当前文件的本地预览 URL (DataURL 或 ObjectURL)
let fileType = ''; // 当前文件类型标识：'pdf' 或 'image'
let pdfDoc = null; // PDF.js 解析后的 PDF 文档实例
let extractResult = []; // 存储最终的提取结果列表（包含字段名、提取值、坐标 bbox 等）
let currentPage = 1; // 当前预览的 PDF 页码 (用于多页 PDF 渲染)
let ocrText = ''; // 纯文本模式下拼接的 OCR 识别文本
let cachedOcrData = null; // 缓存后端返回的原始 OCR 结果，避免在切换模式或重新提取时重复调用耗时的 OCR 接口
let currentProcessMode = 'ocr_only'; // 当前选择的处理模式：'ocr_only' (仅识别) 或 'ocr_and_extract' (识别并提取)
let currentDisplayMode = 'extract_only'; // 结果展示模式：'extract_only' (仅显示提取出的字段) 或 'all_ocr' (显示所有识别出的文本)
let cachedOcrModel = ''; // 记录生成当前缓存 OCR 数据时使用的模型名称，如果用户切换了模型，则需要重新识别
let cachedPdfBlob = null; // 缓存后端生成的双层 PDF Blob 对象，避免重复下载
let cachedPdfFileName = ''; // 缓存生成的 PDF 文件名

// ==================== 第三方库配置 ====================
// 配置 PDF.js 的 Worker 路径，用于在后台线程解析 PDF，避免阻塞主线程
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

// ==================== 页面初始化 ====================
window.onload = function() {
    initTabs(); // 初始化标签页切换逻辑
    loadFieldConfig(); // 从本地存储 (localStorage) 加载上次保存的字段配置
};

/**
 * 初始化顶部标签页 (Tabs) 的点击切换逻辑
 */
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // 如果标签被隐藏 (例如在"仅识别"模式下隐藏了配置标签)，则不允许点击
            if (btn.style.display === 'none') return;
            
            // 移除所有标签和内容的激活状态
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            // 激活当前点击的标签和对应的内容区域
            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });
}

/**
 * 监听"处理模式"单选框的变化，动态显示或隐藏"提取配置方式"选项区域
 */
function toggleExtractOptions() {
    const modeRadios = document.getElementsByName('processMode');
    let isExtract = false;
    // 检查是否选择了"智能信息提取"模式
    for (let radio of modeRadios) {
        if (radio.checked && radio.value === 'ocr_and_extract') {
            isExtract = true;
            break;
        }
    }
    
    const optionsArea = document.getElementById('extractOptionsArea');
    if (isExtract) {
        // 显示配置选项并触发下拉动画
        optionsArea.classList.remove('hidden');
        optionsArea.classList.remove('slide-down');
        void optionsArea.offsetWidth; // 触发浏览器重绘，确保动画重新执行
        optionsArea.classList.add('slide-down');
    } else {
        // 隐藏配置选项
        optionsArea.classList.add('hidden');
        optionsArea.classList.remove('slide-down');
    }
}

// ==================== 智能语义配置 (自然语言解析) ====================

/**
 * 清空自然语言输入框
 */
function clearFreePrompt() {
    document.getElementById('freeExtractPrompt').value = '';
}

/**
 * 调用后端 API，使用大语言模型 (LLM) 解析用户输入的自然语言需求，生成结构化的字段配置
 */
async function parseFreePrompt() {
    const prompt = document.getElementById('freeExtractPrompt').value;
    if (!prompt.trim()) {
        alert('请输入要提取的内容描述');
        return;
    }
    
    // 更新按钮状态为加载中
    const btn = document.querySelector('#config_nl .btn-success');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> AI 正在思考中...';
    btn.disabled = true;
    
    try {
        const baseUrl = getBaseUrl();
        // 发送 POST 请求到后端的 /parse_prompt 接口
        const response = await fetch(`${baseUrl}/parse_prompt`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ prompt: prompt })
        });
        
        if (!response.ok) {
            throw new Error('解析请求失败');
        }
        
        const data = await response.json();
        
        // 如果后端成功返回了解析后的字段列表
        if (data.fields && data.fields.length > 0) {
            // 将后端返回的数据格式映射为前端使用的 fieldList 格式
            fieldList = data.fields.map((f, index) => ({
                id: index + 1,
                name: f.key,
                type: f.field_type === 'string' ? 'text' : f.field_type,
                maxLength: 0,
                regex: '',
                description: f.description || ''
            }));
            
            // 渲染解析结果表格并显示
            renderNlFieldTable();
            document.getElementById('parsedFieldsArea').classList.remove('hidden');
        } else {
            alert('AI 未能从您的描述中解析出明确的字段，请尝试更清晰地描述。');
        }
    } catch (error) {
        console.error('解析失败', error);
        alert('调用 AI 解析失败，请检查后端服务。');
    } finally {
        // 恢复按钮状态
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

        function renderNlFieldTable() {
            const tbody = document.getElementById('nlFieldTableBody');
            tbody.innerHTML = '';
            
            fieldList.forEach((field, index) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${index + 1}</td>
                    <td><input type="text" value="${escapeHtml(field.name)}" onchange="updateField(${field.id}, 'name', this.value)"></td>
                    <td><input type="text" value="${escapeHtml(field.description || '')}" onchange="updateField(${field.id}, 'description', this.value)" placeholder="字段说明"></td>
                    <td class="action-btns">
                        <button class="btn btn-danger" onclick="deleteField(${field.id}, true)"><i class="fas fa-trash"></i> 删除</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

// ==================== 手动结构化规则配置 ====================

/**
 * 手动添加一个新的提取字段规则
 */
function addField() {
    // 获取表单输入值
    const name = document.getElementById('fieldName').value.trim();
    const type = document.getElementById('fieldType').value;
    const maxLength = parseInt(document.getElementById('maxLength').value) || 0;
    const regex = document.getElementById('regexRule').value.trim();
    
    if (!name) {
        alert('请输入字段名称');
        return;
    }
    
    // 生成自增 ID
    const newId = fieldList.length > 0 ? Math.max(...fieldList.map(f => f.id)) + 1 : 1;
    
    // 添加到全局字段列表
    fieldList.push({
        id: newId,
        name: name,
        type: type,
        maxLength: maxLength,
        regex: regex
    });
    
    // 清空输入框，方便继续添加
    document.getElementById('fieldName').value = '';
    document.getElementById('fieldType').value = 'text';
    document.getElementById('maxLength').value = '0';
    document.getElementById('regexRule').value = '';
    
    // 重新渲染表格
    renderFieldTable();
}

        function renderFieldTable() {
            const tbody = document.getElementById('fieldTableBody');
            tbody.innerHTML = '';
            
            fieldList.forEach((field, index) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${index + 1}</td>
                    <td><input type="text" value="${escapeHtml(field.name)}" onchange="updateField(${field.id}, 'name', this.value)"></td>
                    <td>
                        <select onchange="updateField(${field.id}, 'type', this.value)">
                            ${generateTypeOptions(field.type)}
                        </select>
                    </td>
                    <td><input type="number" value="${field.maxLength}" min="0" onchange="updateField(${field.id}, 'maxLength', this.value)"></td>
                    <td><input type="text" value="${escapeHtml(field.regex || '')}" placeholder="正则规则" onchange="updateField(${field.id}, 'regex', this.value)"></td>
                    <td class="action-btns">
                        <button class="btn btn-danger" onclick="deleteField(${field.id})"><i class="fas fa-trash"></i> 删除</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        function generateTypeOptions(selectedType) {
            const types = [
                { value: 'text', label: '文本' },
                { value: 'number', label: '数字' },
                { value: 'date', label: '日期' },
                { value: 'idcard', label: '身份证号' },
                { value: 'phone', label: '手机号' },
                { value: 'email', label: '邮箱' },
                { value: 'money', label: '金额' },
                { value: 'address', label: '地址' }
            ];
            
            return types.map(t => 
                `<option value="${t.value}" ${t.value === selectedType ? 'selected' : ''}>${t.label}</option>`
            ).join('');
        }

        function updateField(id, key, value) {
            const field = fieldList.find(f => f.id === id);
            if (field) {
                if (key === 'maxLength') {
                    field[key] = parseInt(value) || 0;
                } else {
                    field[key] = value;
                }
            }
        }

        function deleteField(id, isNl = false) {
            if (confirm('确定要删除这个字段吗？')) {
                fieldList = fieldList.filter(f => f.id !== id);
                if (isNl) {
                    renderNlFieldTable();
                } else {
                    renderFieldTable();
                }
            }
        }

        function saveFieldConfig() {
            localStorage.setItem('fieldConfig', JSON.stringify(fieldList));
            alert('配置保存成功！');
        }

        function loadFieldConfig() {
            const saved = localStorage.getItem('fieldConfig');
            if (saved) {
                try {
                    fieldList = JSON.parse(saved);
                    renderFieldTable();
                } catch (e) {
                    console.error('加载配置失败', e);
                }
            }
        }

        function clearFieldConfig() {
            if (confirm('确定要清空所有字段配置吗？')) {
                fieldList = [];
                renderFieldTable();
                localStorage.removeItem('fieldConfig');
            }
        }

        function loadSampleConfig() {
            fieldList = [
                { id: 1, name: '甲方名称', type: 'text', maxLength: 100, regex: '' },
                { id: 2, name: '合同金额', type: 'money', maxLength: 20, regex: '^\\d+(\\.\\d{1,2})?$' },
                { id: 3, name: '签订日期', type: 'date', maxLength: 10, regex: '^\\d{4}-\\d{2}-\\d{2}$' },
                { id: 4, name: '身份证号', type: 'idcard', maxLength: 18, regex: '^\\d{17}[\\dXx]$' },
                { id: 5, name: '联系电话', type: 'phone', maxLength: 11, regex: '^1[3-9]\\d{9}$' }
            ];
            renderFieldTable();
            saveFieldConfig();
        }

        function exportFieldConfig() {
            if (fieldList.length === 0) {
                alert('当前没有配置任何字段，无法导出。');
                return;
            }
            const configJson = JSON.stringify(fieldList, null, 2);
            downloadFile(configJson, '字段配置.json', 'application/json');
        }

        function importFieldConfig(event) {
            const file = event.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const importedConfig = JSON.parse(e.target.result);
                    if (Array.isArray(importedConfig)) {
                        // 简单的格式校验
                        const isValid = importedConfig.every(item => item.hasOwnProperty('name') && item.hasOwnProperty('type'));
                        if (isValid) {
                            fieldList = importedConfig;
                            // 重新分配ID以防冲突
                            fieldList.forEach((f, index) => f.id = index + 1);
                            renderFieldTable();
                            saveFieldConfig();
                            alert('配置导入成功！');
                        } else {
                            alert('导入的配置文件格式不正确。');
                        }
                    } else {
                        alert('导入的配置文件格式不正确，应为数组。');
                    }
                } catch (error) {
                    console.error('解析配置文件失败', error);
                    alert('解析配置文件失败，请确保文件是有效的JSON格式。');
                }
                // 清空 input 的值，以便可以重复导入同一个文件
                event.target.value = '';
            };
            reader.readAsText(file);
        }

// ==================== 文件上传与预览 ====================

/**
 * 处理文件选择事件
 */
function handleFileUpload() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    
    if (!file) return;
    
    currentFile = file;
    const fileSize = file.size / 1024 / 1024; // 转换为 MB
    
    // 限制文件大小
    if (fileSize > 50) {
        alert('文件大小不能超过50MB');
        return;
    }
    
    // 简单判断文件类型 (基于 MIME type)
    if (file.type.includes('pdf')) {
        fileType = 'pdf';
    } else if (file.type.includes('image')) {
        fileType = 'image';
    } else {
        alert('不支持的文件类型，请上传 PDF 或图片');
        return;
    }
    
    // 在界面上预览文件
    previewFile(file);
    
    // 文件上传成功后，显示"启动分析流程"按钮
    document.getElementById('confirmBtn').classList.remove('hidden');
    
    // 上传了新文件，必须清除旧的缓存数据
    cachedOcrData = null;
    cachedPdfBlob = null;
    cachedPdfFileName = '';
}

        function previewFile(file) {
            const previewArea = document.getElementById('previewArea');
            
            // 清除旧内容
            previewArea.innerHTML = '';
            
            if (file.type.includes('image')) {
                // 图片预览
                previewArea.style.display = 'block';
                previewArea.style.padding = '20px 0';
                previewArea.style.textAlign = 'center';
                const reader = new FileReader();
                reader.onload = function(e) {
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    img.style.maxWidth = '100%';
                    img.style.maxHeight = '800px';
                    img.style.display = 'inline-block';
                    previewArea.appendChild(img);
                    currentFileUrl = e.target.result;
                };
                reader.readAsDataURL(file);
            } else if (file.type.includes('pdf')) {
                // PDF预览（全部页面）
                const reader = new FileReader();
                reader.onload = function(e) {
                    const pdfData = new Uint8Array(e.target.result);
                    pdfjsLib.getDocument({ data: pdfData }).promise.then(async function(pdf) {
                        pdfDoc = pdf;
                        previewArea.innerHTML = '';
                        previewArea.style.display = 'block';
                        previewArea.style.padding = '20px 0';
                        previewArea.style.textAlign = 'center';
                        
                        for (let i = 1; i <= pdf.numPages; i++) {
                            const page = await pdf.getPage(i);
                            const viewport = page.getViewport({ scale: 1.5 });
                            const canvas = document.createElement('canvas');
                            canvas.style.maxWidth = '100%';
                            canvas.style.height = 'auto';
                            canvas.style.marginBottom = '20px';
                            canvas.style.display = 'inline-block';
                            
                            const context = canvas.getContext('2d');
                            canvas.height = viewport.height;
                            canvas.width = viewport.width;
                            
                            await page.render({
                                canvasContext: context,
                                viewport: viewport
                            }).promise;
                            
                            previewArea.appendChild(canvas);
                            previewArea.appendChild(document.createElement('br'));
                        }
                    }).catch(function(error) {
                        console.error('PDF预览失败', error);
                        previewArea.innerHTML = '<p style="color: red; text-align: center; line-height: 500px;">PDF预览失败，请重试</p>';
                    });
                };
                reader.readAsArrayBuffer(file);
            }
        }

// ==================== 核心业务流程控制 ====================

/**
 * 获取后端 API 的基础 URL。
 * 兼容本地开发环境 (8000端口) 和生产部署环境 (相对路径)。
 */
function getBaseUrl() {
    const host = window.location.hostname;
    if (host === '127.0.0.1' || host === 'localhost' || host.startsWith('192.168.')) {
        return `http://${host}:8000/api/v1`;
    } else {
        return '/api/v1';
    }
}

/**
 * 点击"启动分析流程"按钮后的主控逻辑。
 * 负责调用 OCR 接口，并根据用户选择的模式决定后续跳转。
 */
async function confirmAndProcess() {
    if (!currentFile) {
        alert('请先上传文档');
        return;
    }

    // 获取当前选择的处理模式
    const modeRadios = document.getElementsByName('processMode');
    for (let radio of modeRadios) {
        if (radio.checked) {
            currentProcessMode = radio.value;
            break;
        }
    }

    // 显示进度条
    const progress = document.getElementById('extractProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const logArea = document.getElementById('ocrLogArea');
    
    progress.classList.remove('hidden');
    if (logArea) {
        logArea.classList.remove('hidden');
        logArea.innerHTML = '';
    }
    progressFill.style.width = '10%';
    progressText.textContent = '正在上传并进行OCR识别...';

    let logInterval = null;
    let taskId = 'task_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

    try {
        const selectedModel = document.getElementById('ocrModelSelect').value;
        
        // 1. 执行 OCR 识别
        // 优化：如果当前文件已经识别过，且使用的模型没有改变，则直接使用缓存数据，跳过网络请求
        if (!cachedOcrData || cachedOcrModel !== selectedModel) {
            const formData = new FormData();
            formData.append('file', currentFile);
            formData.append('ocr_service', selectedModel);
            formData.append('task_id', taskId);
            
            const baseUrl = getBaseUrl();

            // 发送 OCR 请求
            const ocrResponse = await fetch(`${baseUrl}/ocr`, {
                method: 'POST',
                body: formData
            });
            
            if (!ocrResponse.ok) {
                const errData = await ocrResponse.json().catch(() => ({}));
                throw new Error(`OCR请求失败: ${errData.detail || ocrResponse.statusText}`);
            }
            
            // 缓存 OCR 结果
            cachedOcrData = await ocrResponse.json();
            
            // 记录原始图像尺寸，用于后续绘制红框时的坐标换算
            if (cachedOcrData.pages && cachedOcrData.pages.length > 0) {
                window.originalImageWidth = cachedOcrData.pages[0].image_width;
                window.originalImageHeight = cachedOcrData.pages[0].image_height;
            }
            cachedOcrModel = selectedModel;
            // 清除旧的 PDF 缓存，因为 OCR 数据已更新
            cachedPdfBlob = null;
            cachedPdfFileName = '';
        }

        // 更新进度条状态
        progressFill.style.width = '100%';
        progressText.textContent = 'OCR识别完成！';
        if (logArea) {
            logArea.innerHTML += '<br><strong>OCR识别完成！</strong>';
            logArea.scrollTop = logArea.scrollHeight;
        }

        // 延迟 1 秒后进行页面跳转，让用户看清完成状态
        setTimeout(() => {
            progress.classList.add('hidden');
            if (logArea) logArea.classList.add('hidden');
            
            // 2. 根据处理模式决定下一步路由
            if (currentProcessMode === 'ocr_only') {
                // 模式 A：仅识别模式
                // 隐藏配置标签，直接跳转到结果页展示纯文本
                document.getElementById('tabConfigNl').style.display = 'none';
                document.getElementById('tabConfigManual').style.display = 'none';
                document.getElementById('displayModeToggle').classList.add('hidden');
                
                showOcrResultsOnly();
                document.querySelector('[data-tab="result"]').click();
            } else {
                // 模式 B：识别并提取模式
                // 根据用户选择的配置方式 (自然语言 vs 手动)，跳转到对应的配置页面
                let configMode = 'nl';
                const configRadios = document.getElementsByName('configMode');
                for (let radio of configRadios) {
                    if (radio.checked) {
                        configMode = radio.value;
                        break;
                    }
                }
                
                document.getElementById('displayModeToggle').classList.remove('hidden');
                
                if (configMode === 'nl') {
                    document.getElementById('tabConfigNl').style.display = 'block';
                    document.getElementById('tabConfigManual').style.display = 'none';
                    document.querySelector('[data-tab="config_nl"]').click();
                } else {
                    document.getElementById('tabConfigNl').style.display = 'none';
                    document.getElementById('tabConfigManual').style.display = 'block';
                    document.querySelector('[data-tab="config_manual"]').click();
                    renderFieldTable(); // 确保表格渲染
                }
            }
        }, 1000);

    } catch (error) {
        // 错误处理
        if (logInterval) clearInterval(logInterval);
        progressText.textContent = '处理失败：' + error.message;
        if (logArea) {
            logArea.innerHTML += `<br><span style="color: red;">处理失败：${error.message}</span>`;
            logArea.scrollTop = logArea.scrollHeight;
        }
        console.error('处理失败', error);
        setTimeout(() => {
            progress.classList.add('hidden');
            if (logArea) logArea.classList.add('hidden');
        }, 3000);
    }
}

        // 仅展示OCR结果
        function showOcrResultsOnly() {
            extractResult = [];
            if (cachedOcrData && cachedOcrData.pages) {
                let idCounter = 1;
                cachedOcrData.pages.forEach((page, pageIndex) => {
                    page.ocr_results.forEach(res => {
                        extractResult.push({
                            fieldId: idCounter++,
                            fieldName: `文本片段 ${idCounter-1}`,
                            value: res.text,
                            isValid: true,
                            isOcrOnly: true, // 标记为纯OCR结果
                            pageIndex: pageIndex,
                            bbox: {
                                x: res.box.x_min,
                                y: res.box.y_min,
                                width: res.box.x_max - res.box.x_min,
                                height: res.box.y_max - res.box.y_min
                            }
                        });
                    });
                });
            }
            renderResultTable();
            showResultPreview();
        }
        
        // 切换结果展示模式 (提取内容 vs 所有的原始OCR文本)
        function toggleResultDisplay() {
            const btn = document.getElementById('toggleDisplayBtn');
            if (currentDisplayMode === 'extract_only') {
                currentDisplayMode = 'all_ocr';
                btn.innerHTML = '<i class="fas fa-exchange-alt"></i> 切换显示：仅提取内容';
            } else {
                currentDisplayMode = 'extract_only';
                btn.innerHTML = '<i class="fas fa-exchange-alt"></i> 切换显示：所有的原始OCR文本';
            }
            renderResultTable();
            showResultPreview();
        }

/**
 * 在配置页面点击"应用规则并执行提取"按钮时触发。
 * 调用后端大模型接口，根据配置的规则从 OCR 结果中提取结构化数据。
 */
async function extractFieldsOnly() {
    // 前置校验
    if (!cachedOcrData) {
        alert('请先返回上传页面完成文档识别');
        document.querySelector('[data-tab="upload"]').click();
        return;
    }
    
    if (fieldList.length === 0) {
        alert('请先配置需要提取的字段');
        return;
    }

    // 将进度条移动到当前可视的 Tab 区域内
    const progress = document.getElementById('extractProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    document.querySelector('.tab-content.active').appendChild(progress);
    
    progress.classList.remove('hidden');
    progressFill.style.width = '50%';
    progressText.textContent = '正在调用大模型提取字段...';

    try {
        // 构造请求后端的规则数据结构
        const rules = fieldList.map(f => ({
            key: f.name,
            field_type: f.type === 'text' ? 'string' : f.type,
            max_length: f.maxLength || null,
            regex: f.regex || null
        }));
        
        // 构造完整的提取请求体
        const extractRequest = {
            pages: cachedOcrData.pages, // 传入之前缓存的 OCR 结果
            rules: rules,
            llm_config: null // 使用后端默认的 LLM 配置
        };
        
        const baseUrl = getBaseUrl();
        // 发送 POST 请求到 /extract_fields 接口
        const extractResponse = await fetch(`${baseUrl}/extract_fields`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(extractRequest)
        });
        
        if (!extractResponse.ok) {
            const errData = await extractResponse.json().catch(() => ({}));
            let errorMsg = errData.detail;
            if (typeof errorMsg === 'object') {
                errorMsg = JSON.stringify(errorMsg);
            }
            throw new Error(`提取请求失败: ${errorMsg || extractResponse.statusText}`);
        }
        
        const extractData = await extractResponse.json();
        
        progressFill.style.width = '100%';
        progressText.textContent = '提取完成！';
        
        // 处理后端返回的提取结果，映射为前端需要的格式
        extractResult = extractData.extracted_data.map((item, index) => {
            let pageIndex = 0;
            // 尝试在原始 OCR 数据中查找该提取项所在的页码 (通过坐标匹配)
            if (item.box && cachedOcrData && cachedOcrData.pages) {
                for (let i = 0; i < cachedOcrData.pages.length; i++) {
                    const page = cachedOcrData.pages[i];
                    const match = page.ocr_results.find(res =>
                        Math.abs(res.box.x_min - item.box.x_min) < 1 &&
                        Math.abs(res.box.y_min - item.box.y_min) < 1
                    );
                    if (match) {
                        pageIndex = i;
                        break;
                    }
                }
            }
            return {
                fieldId: index + 1,
                fieldName: item.key,
                value: item.value,
                isValid: item.is_valid,
                validationError: item.validation_error,
                pageIndex: pageIndex,
                bbox: item.box ? {
                    x: item.box.x_min,
                    y: item.box.y_min,
                    width: item.box.x_max - item.box.x_min,
                    height: item.box.y_max - item.box.y_min
                } : null
            };
        });
        
        // 跳转到结果展示页并渲染
        document.querySelector('[data-tab="result"]').click();
        renderResultTable();
        showResultPreview();
        
        // 延迟隐藏进度条并将其移回原位
        setTimeout(() => {
            progress.classList.add('hidden');
            document.getElementById('upload').appendChild(progress);
        }, 1000);
        
    } catch (error) {
        progressText.textContent = '提取失败：' + error.message;
        console.error('提取失败', error);
        setTimeout(() => {
            progress.classList.add('hidden');
            document.getElementById('upload').appendChild(progress);
        }, 3000);
    }
}

        // ==================== 结果展示功能 ====================
        function renderOcrTextElements(dataList, container) {
            container.innerHTML = '';
            
            const sortedResults = [...dataList].sort((a, b) => {
                if (!a.bbox || !b.bbox) return 0;
                // 首先按页码排序
                if (a.pageIndex !== b.pageIndex) {
                    return a.pageIndex - b.pageIndex;
                }
                // 同一页内按 Y 坐标排序
                if (Math.abs(a.bbox.y - b.bbox.y) > 10) {
                    return a.bbox.y - b.bbox.y;
                }
                // 同一行内按 X 坐标排序
                return a.bbox.x - b.bbox.x;
            });
            
            let currentLineY = -1;
            let currentPageIndex = -1;
            let lineDiv = null;
            
            sortedResults.forEach(item => {
                // 如果是新的一页，或者 Y 坐标变化超过 10 像素，则创建新行
                if (currentPageIndex !== item.pageIndex || currentLineY === -1 || Math.abs(item.bbox.y - currentLineY) > 10) {
                    // 如果是新的一页，可以添加一个页码分隔符 (可选)
                    if (currentPageIndex !== -1 && currentPageIndex !== item.pageIndex) {
                        const pageDivider = document.createElement('div');
                        pageDivider.style.borderTop = '1px dashed #ccc';
                        pageDivider.style.margin = '15px 0';
                        pageDivider.style.color = '#999';
                        pageDivider.style.fontSize = '12px';
                        pageDivider.style.textAlign = 'center';
                        pageDivider.textContent = `--- 第 ${item.pageIndex + 1} 页 ---`;
                        container.appendChild(pageDivider);
                    }
                    
                    currentLineY = item.bbox.y;
                    currentPageIndex = item.pageIndex;
                    lineDiv = document.createElement('div');
                    lineDiv.style.marginBottom = '5px';
                    container.appendChild(lineDiv);
                }
                
                const span = document.createElement('span');
                span.textContent = item.value + ' ';
                span.className = 'ocr-text-span';
                span.style.cursor = 'pointer';
                span.style.padding = '2px 4px';
                span.style.borderRadius = '3px';
                span.style.transition = 'background 0.2s';
                span.setAttribute('data-field-id', item.fieldId);
                
                span.onmouseover = function() {
                    if (this.style.background !== 'rgb(255, 243, 205)' && this.style.background !== '#fff3cd') {
                        this.style.background = '#e8f4fd';
                    }
                };
                span.onmouseout = function() {
                    if (this.style.background !== 'rgb(255, 243, 205)' && this.style.background !== '#fff3cd') {
                        this.style.background = 'transparent';
                    }
                };
                
                span.onclick = function() {
                    highlightField(item);
                };
                
                lineDiv.appendChild(span);
            });
        }

        function getAllOcrData() {
            let displayData = [];
            if (cachedOcrData && cachedOcrData.pages) {
                cachedOcrData.pages.forEach((page, pageIndex) => {
                    let idCounter = 1000 + pageIndex * 1000;
                    page.ocr_results.forEach(res => {
                        displayData.push({
                            fieldId: idCounter++,
                            value: res.text,
                            pageIndex: pageIndex,
                            bbox: {
                                x: res.box.x_min,
                                y: res.box.y_min,
                                width: res.box.x_max - res.box.x_min,
                                height: res.box.y_max - res.box.y_min
                            }
                        });
                    });
                });
            }
            return displayData;
        }

        function getSortedOcrTextLines(dataList) {
            const sortedResults = [...dataList].sort((a, b) => {
                if (!a.bbox || !b.bbox) return 0;
                // 首先按页码排序，确保不同页的文字不会混在一起
                if (a.pageIndex !== b.pageIndex) {
                    return a.pageIndex - b.pageIndex;
                }
                // 同一页内，按 Y 坐标排序 (允许 10 像素的误差视为同一行)
                if (Math.abs(a.bbox.y - b.bbox.y) > 10) {
                    return a.bbox.y - b.bbox.y;
                }
                // 同一行内，按 X 坐标排序
                return a.bbox.x - b.bbox.x;
            });
            
            let currentLineY = -1;
            let currentPageIndex = -1;
            let currentLineText = "";
            let lines = [];
            
            sortedResults.forEach(item => {
                if (currentLineY === -1) {
                    currentLineY = item.bbox.y;
                    currentPageIndex = item.pageIndex;
                    currentLineText = item.value;
                } else if (item.pageIndex === currentPageIndex && Math.abs(item.bbox.y - currentLineY) <= 10) {
                    // 同一页且在同一行
                    currentLineText += " " + item.value;
                } else {
                    // 换行或换页
                    lines.push(currentLineText);
                    currentLineY = item.bbox.y;
                    currentPageIndex = item.pageIndex;
                    currentLineText = item.value;
                }
            });
            if (currentLineText) {
                lines.push(currentLineText);
            }
            return lines;
        }

        function renderResultTable() {
            const tbody = document.getElementById('resultTableBody');
            const table = document.getElementById('resultTable');
            let ocrTextDiv = document.getElementById('ocrOnlyResultText');
            
            if (!ocrTextDiv) {
                ocrTextDiv = document.createElement('div');
                ocrTextDiv.id = 'ocrOnlyResultText';
                ocrTextDiv.style.cssText = 'background: white; padding: 20px; border-radius: 6px; border: 1px solid #ddd; font-family: monospace; line-height: 1.8; min-height: 200px; margin-top: 0; font-size: 16px;';
                document.getElementById('resultTableContainer').appendChild(ocrTextDiv);
            }
            
            tbody.innerHTML = '';
            
            const isOcrOnlyMode = currentProcessMode === 'ocr_only';
            const showAsText = isOcrOnlyMode || currentDisplayMode === 'all_ocr';
            
            if (showAsText) {
                table.classList.add('hidden');
                ocrTextDiv.classList.remove('hidden');
                
                let displayData = [];
                if (isOcrOnlyMode) {
                    displayData = extractResult;
                } else {
                    displayData = getAllOcrData();
                }
                
                renderOcrTextElements(displayData, ocrTextDiv);
                
            } else {
                table.classList.remove('hidden');
                ocrTextDiv.classList.add('hidden');
                
                document.querySelectorAll('.validation-col, .action-col').forEach(el => {
                    el.style.display = '';
                });
                
                extractResult.forEach((item, index) => {
                    const tr = document.createElement('tr');
                    tr.className = 'clickable-row';
                    tr.setAttribute('data-field-id', item.fieldId);
                    tr.setAttribute('data-index', index);
                    tr.onclick = function() { highlightField(item); };
                    
                    let statusBadge = item.isValid
                        ? '<span class="badge badge-success">校验通过</span>'
                        : `<span class="badge badge-danger" title="${item.validationError || '校验失败'}">校验失败</span>`;
                    
                    const displayValue = `<span class="text-gray">${escapeHtml(item.fieldName)}：</span> <strong>${escapeHtml(String(item.value))}</strong>`;
                    
                    tr.innerHTML = `
                        <td>${escapeHtml(item.fieldName)}</td>
                        <td>${displayValue}</td>
                        <td>${statusBadge}</td>
                        <td>
                            <button class="btn btn-info" onclick="event.stopPropagation(); copySingleResult(${index})">
                                <i class="fas fa-copy"></i> 复制
                            </button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }

        function showResultPreview() {
            const previewArea = document.getElementById('resultPreviewArea');
            previewArea.innerHTML = '';
            previewArea.style.display = 'block';
            previewArea.style.overflow = 'auto';
            previewArea.style.textAlign = 'center';
            previewArea.style.padding = '20px 0';
            
            if (!currentFileUrl && fileType !== 'pdf') {
                // 如果没有上传的文件，显示模拟预览
                showMockPreview();
                return;
            }
            
            if (fileType === 'image' && currentFileUrl) {
                const wrapper = document.createElement('div');
                wrapper.style.marginBottom = '20px';
                
                const container = document.createElement('div');
                container.className = 'result-preview-container';
                container.style.position = 'relative';
                container.style.display = 'inline-block';
                
                const img = document.createElement('img');
                img.src = currentFileUrl;
                img.style.display = 'block';
                img.style.maxWidth = '100%';
                img.style.height = 'auto';
                
                img.onload = function() {
                    drawBBoxes(container, img, 0);
                };
                container.appendChild(img);
                wrapper.appendChild(container);
                previewArea.appendChild(wrapper);
            } else if (fileType === 'pdf' && pdfDoc) {
                (async function() {
                    for (let i = 1; i <= pdfDoc.numPages; i++) {
                        const wrapper = document.createElement('div');
                        wrapper.style.marginBottom = '20px';
                        
                        const container = document.createElement('div');
                        container.className = 'result-preview-container';
                        container.style.position = 'relative';
                        container.style.display = 'inline-block';
                        
                        const page = await pdfDoc.getPage(i);
                        const viewport = page.getViewport({ scale: 1.5 }); // 降低一点 scale，避免过大
                        const canvas = document.createElement('canvas');
                        const context = canvas.getContext('2d');
                        canvas.height = viewport.height;
                        canvas.width = viewport.width;
                        canvas.style.display = 'block';
                        canvas.style.maxWidth = '100%';
                        canvas.style.height = 'auto';
                        
                        await page.render({
                            canvasContext: context,
                            viewport: viewport
                        }).promise;
                        
                        container.appendChild(canvas);
                        wrapper.appendChild(container);
                        previewArea.appendChild(wrapper);
                        
                        drawBBoxes(container, canvas, i - 1);
                    }
                })();
            } else {
                showMockPreview();
                return;
            }
        }

        function showMockPreview() {
            const previewArea = document.getElementById('resultPreviewArea');
            previewArea.innerHTML = '';
            previewArea.style.display = 'flex';
            
            const container = document.createElement('div');
            container.className = 'result-preview-container';
            container.style.position = 'relative';
            container.style.width = '800px';
            container.style.height = '600px';
            container.style.background = '#f0f0f0';
            container.style.border = '1px solid #ddd';
            container.style.display = 'flex';
            container.style.alignItems = 'center';
            container.style.justifyContent = 'center';
            
            const mockText = document.createElement('div');
            mockText.innerHTML = '<p style="color: #666;">文档预览区域<br><small>（实际使用时上传文档会显示真实预览）</small></p>';
            container.appendChild(mockText);
            
            previewArea.appendChild(container);
        }

/**
 * 在预览图像上绘制识别结果的边界框 (Bounding Box)
 * @param {HTMLElement} container - 包含图像的容器元素
 * @param {HTMLElement} element - 图像元素 (img 或 canvas)
 * @param {number} pageIndex - 当前页码索引
 */
function drawBBoxes(container, element, pageIndex) {
    // 清除旧的边框
    const oldBoxes = container.querySelectorAll('.bbox-highlight');
    oldBoxes.forEach(box => box.remove());
    
    // 获取图像的原始物理尺寸，用于计算相对坐标
    const originalWidth = element.naturalWidth || (cachedOcrData && cachedOcrData.pages[pageIndex] ? cachedOcrData.pages[pageIndex].image_width : window.originalImageWidth) || element.width;
    const originalHeight = element.naturalHeight || (cachedOcrData && cachedOcrData.pages[pageIndex] ? cachedOcrData.pages[pageIndex].image_height : window.originalImageHeight) || element.height;
    
    if (!originalWidth || !originalHeight) return;
    
    // 确定需要绘制的数据源
    let boxesToDraw = extractResult.filter(item => item.pageIndex === pageIndex);
    // 如果处于"显示所有OCR文本"模式，则绘制所有原始 OCR 框
    if (currentProcessMode !== 'ocr_only' && currentDisplayMode === 'all_ocr') {
        boxesToDraw = [];
        if (cachedOcrData && cachedOcrData.pages && cachedOcrData.pages[pageIndex]) {
            let idCounter = 1000 + pageIndex * 1000;
            cachedOcrData.pages[pageIndex].ocr_results.forEach(res => {
                boxesToDraw.push({
                    fieldId: idCounter++,
                    bbox: {
                        x: res.box.x_min,
                        y: res.box.y_min,
                        width: res.box.x_max - res.box.x_min,
                        height: res.box.y_max - res.box.y_min
                    }
                });
            });
        }
    }
    
    // 遍历数据并创建 DOM 元素绘制边框
    boxesToDraw.forEach(item => {
        if (item.bbox) {
            const bboxDiv = document.createElement('div');
            bboxDiv.className = 'bbox-highlight';
            bboxDiv.style.position = 'absolute';
            bboxDiv.style.border = '2px solid red';
            bboxDiv.style.background = 'rgba(255, 0, 0, 0.1)';
            
            // 核心逻辑：使用百分比定位。
            // 这样无论外层容器或图片如何被 CSS 缩放 (例如 max-width: 100%)，红框都能精确对齐到文字上。
            bboxDiv.style.left = (item.bbox.x / originalWidth * 100) + '%';
            bboxDiv.style.top = (item.bbox.y / originalHeight * 100) + '%';
            bboxDiv.style.width = (item.bbox.width / originalWidth * 100) + '%';
            bboxDiv.style.height = (item.bbox.height / originalHeight * 100) + '%';
            bboxDiv.setAttribute('data-field-id', item.fieldId);
            
            // 添加点击事件，实现图文联动高亮
            bboxDiv.style.cursor = 'pointer';
            bboxDiv.onclick = function(e) {
                e.stopPropagation();
                highlightField(item);
            };
            
            container.appendChild(bboxDiv);
        }
    });
}

        function highlightField(item) {
            document.querySelectorAll('.bbox-highlight').forEach(box => {
                box.style.border = '2px solid red';
                box.style.background = 'rgba(255, 0, 0, 0.1)';
            });
            
            const targetBox = document.querySelector(`.bbox-highlight[data-field-id="${item.fieldId}"]`);
            if (targetBox) {
                targetBox.style.border = '3px solid #ffeb3b';
                targetBox.style.background = 'rgba(255, 235, 59, 0.3)';
                targetBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            
            document.querySelectorAll('#resultTableBody tr').forEach(tr => {
                tr.style.background = '';
            });
            const targetRow = document.querySelector(`#resultTableBody tr[data-field-id="${item.fieldId}"]`);
            if (targetRow) {
                targetRow.style.background = '#fff3cd';
            }
            
            document.querySelectorAll('.ocr-text-span').forEach(span => {
                span.style.background = 'transparent';
            });
            const targetSpan = document.querySelector(`.ocr-text-span[data-field-id="${item.fieldId}"]`);
            if (targetSpan) {
                targetSpan.style.background = '#fff3cd';
            }
        }

        function copySingleResult(index) {
            const item = extractResult[index];
            const text = item.value;
            
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    showNotification('已复制: ' + text);
                }).catch(() => {
                    alert('复制失败');
                });
            } else {
                // Fallback
                const textArea = document.createElement("textarea");
                textArea.value = text;
                textArea.style.position = "fixed";
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                try {
                    document.execCommand('copy');
                    showNotification('已复制: ' + text);
                } catch (err) {
                    alert('复制失败');
                }
                document.body.removeChild(textArea);
            }
        }

        // ==================== 导出功能 ====================
        function getExportFileName(extension) {
            const originalName = currentFile ? currentFile.name : '未知文件';
            // 移除原始扩展名
            const nameWithoutExt = originalName.substring(0, originalName.lastIndexOf('.')) || originalName;
            return `识别结果_${nameWithoutExt}.${extension}`;
        }

        // Helper function to get sorted lines for layout preservation
        function getSortedExtractedLines(dataList) {
            const sortedResults = [...dataList]
                .filter(item => item.bbox)
                .sort((a, b) => {
                    if (Math.abs(a.bbox.y - b.bbox.y) > 15) { // Increased threshold for line breaks
                        return a.bbox.y - b.bbox.y;
                    }
                    return a.bbox.x - b.bbox.x;
                });

            if (sortedResults.length === 0) return [];

            let lines = [];
            let currentLine = [{ name: sortedResults[0].fieldName, value: sortedResults[0].value }];
            let currentLineY = sortedResults[0].bbox.y;

            for (let i = 1; i < sortedResults.length; i++) {
                const item = sortedResults[i];
                if (Math.abs(item.bbox.y - currentLineY) <= 15) {
                    currentLine.push({ name: item.fieldName, value: item.value });
                } else {
                    lines.push(currentLine);
                    currentLine = [{ name: item.fieldName, value: item.value }];
                    currentLineY = item.bbox.y;
                }
            }
            lines.push(currentLine);
            return lines;
        }

        function exportResults() {
            let results;
            if (currentProcessMode === 'ocr_only' || currentDisplayMode === 'all_ocr') {
                const dataToExport = currentProcessMode === 'ocr_only' ? extractResult : getAllOcrData();
                const lines = getSortedOcrTextLines(dataToExport);
                results = {
                    extractTime: new Date().toISOString(),
                    mode: currentProcessMode === 'ocr_only' ? 'ocr_only' : 'all_ocr',
                    text: lines.join('\n')
                };
            } else {
                results = {
                    extractTime: new Date().toISOString(),
                    mode: 'extract_only',
                    fields: extractResult.map(item => ({
                        name: item.fieldName,
                        value: item.value,
                        isValid: item.isValid
                    }))
                };
            }
            
            const fileName = getExportFileName('json');
            downloadFile(JSON.stringify(results, null, 2), fileName, 'application/json');
        }

        function exportResultsMarkdown() {
            let mdContent = [];
            
            if (currentProcessMode === 'ocr_only' || currentDisplayMode === 'all_ocr') {
                const dataToExport = currentProcessMode === 'ocr_only' ? extractResult : getAllOcrData();
                const lines = getSortedOcrTextLines(dataToExport);
                mdContent = lines;
            } else {
                const lines = getSortedExtractedLines(extractResult);
                lines.forEach(line => {
                    const lineText = line.map(item => `**${item.name}**: ${item.value}`).join('   ');
                    mdContent.push(lineText);
                });
            }
            
            const text = mdContent.join('\n\n');
            const fileName = getExportFileName('md');
            downloadFile(text, fileName, 'text/markdown;charset=utf-8;');
        }

        function exportResultsDocx() {
            if (typeof docx === 'undefined') {
                alert('Word导出库加载失败，请检查网络');
                return;
            }
            
            const { Document, Packer, Paragraph, TextRun } = docx;
            let children = [];
            
            children.push(new Paragraph({ children: [new TextRun({ text: "信息提取结果", bold: true, size: 32, font: "SimSun" })] }));
            children.push(new Paragraph(""));

            if (currentProcessMode === 'ocr_only' || currentDisplayMode === 'all_ocr') {
                const dataToExport = currentProcessMode === 'ocr_only' ? extractResult : getAllOcrData();
                const lines = getSortedOcrTextLines(dataToExport);
                lines.forEach(line => {
                    children.push(new Paragraph({ children: [new TextRun({ text: line, font: "SimSun" })] }));
                });
            } else {
                const lines = getSortedExtractedLines(extractResult);
                lines.forEach(line => {
                    const textRuns = [];
                    line.forEach((item, index) => {
                        textRuns.push(new TextRun({ text: item.name + '：', bold: true, font: "SimSun" }));
                        textRuns.push(new TextRun({ text: String(item.value) + '   ', font: "SimSun" }));
                    });
                    children.push(new Paragraph({ children: textRuns }));
                });
            }
            
            const doc = new Document({
                sections: [{
                    properties: {},
                    children: children,
                }],
            });
            
            Packer.toBlob(doc).then(blob => {
                const fileName = getExportFileName('docx');
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = fileName;
                link.click();
                URL.revokeObjectURL(link.href);
            });
        }

        function exportResultsCSV() {
            // 添加 BOM (Byte Order Mark) 以解决 Excel 打开 CSV 乱码问题
            let csv = '\uFEFF';
            
            if (currentProcessMode === 'ocr_only' || currentDisplayMode === 'all_ocr') {
                csv += '识别内容\n';
                const dataToExport = currentProcessMode === 'ocr_only' ? extractResult : getAllOcrData();
                const lines = getSortedOcrTextLines(dataToExport);
                lines.forEach(line => {
                    const safeValue = String(line).replace(/"/g, '""');
                    csv += `"${safeValue}"\n`;
                });
            } else {
                csv += '字段名称,提取值,校验结果\n';
                extractResult.forEach(item => {
                    // 处理值中可能包含的引号，将其转义为双引号
                    const safeValue = String(item.value).replace(/"/g, '""');
                    const safeName = String(item.fieldName).replace(/"/g, '""');
                    
                    const row = [
                        `"${safeName}"`,
                        `"${safeValue}"`,
                        item.isValid ? '通过' : '失败'
                    ].join(',');
                    csv += row + '\n';
                });
            }
            
            const fileName = getExportFileName('csv');
            downloadFile(csv, fileName, 'text/csv;charset=utf-8;');
        }

        function showNotification(message) {
            let toast = document.getElementById('toastNotification');
            if (!toast) {
                toast = document.createElement('div');
                toast.id = 'toastNotification';
                toast.className = 'toast-notification';
                document.body.appendChild(toast);
            }
            toast.innerHTML = `<i class="fas fa-info-circle"></i> ${message}`;
            
            // Force reflow
            void toast.offsetWidth;
            
            toast.classList.add('show');
            
            setTimeout(() => {
                toast.classList.remove('show');
            }, 5000);
        }

        async function exportResultsPDF() {
            if (!cachedOcrData) {
                alert('没有可导出的数据，请先进行识别。');
                return;
            }
            
            if (cachedPdfBlob && cachedPdfFileName) {
                showNotification('正在下载已生成的PDF...');
                if (window.navigator && window.navigator.msSaveOrOpenBlob) {
                    window.navigator.msSaveOrOpenBlob(cachedPdfBlob, cachedPdfFileName);
                } else {
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(cachedPdfBlob);
                    link.download = cachedPdfFileName;
                    link.style.display = 'none';
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    document.body.appendChild(link);
                    link.click();
                    setTimeout(() => {
                        document.body.removeChild(link);
                        URL.revokeObjectURL(link.href);
                    }, 100);
                }
                return;
            }
            
            // showNotification('导出pdf大约需要1分钟的时间，请耐心等待！');
            
            const btn = document.querySelector('button[onclick="exportResultsPDF()"]');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
            btn.disabled = true;
            
            try {
                const formData = new FormData();
                formData.append('ocr_data', JSON.stringify(cachedOcrData));
                
                const baseUrl = getBaseUrl();
                const response = await fetch(`${baseUrl}/generate_pdf`, {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    throw new Error('生成PDF失败');
                }
                
                const blob = await response.blob();
                const fileName = getExportFileName('pdf');
                
                cachedPdfBlob = blob;
                cachedPdfFileName = fileName;
                
                // 兼容不同浏览器的下载方式
                if (window.navigator && window.navigator.msSaveOrOpenBlob) {
                    // IE/Edge
                    window.navigator.msSaveOrOpenBlob(blob, fileName);
                } else {
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = fileName;
                    link.style.display = 'none';
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    document.body.appendChild(link);
                    link.click();
                    setTimeout(() => {
                        document.body.removeChild(link);
                        URL.revokeObjectURL(link.href);
                    }, 100);
                }
                
            } catch (error) {
                console.error('导出PDF失败', error);
                alert('导出PDF失败，请检查后端服务。');
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }

        function copyResults() {
            let text = '';
            if (currentProcessMode === 'ocr_only' || currentDisplayMode === 'all_ocr') {
                const dataToExport = currentProcessMode === 'ocr_only' ? extractResult : getAllOcrData();
                const lines = getSortedOcrTextLines(dataToExport);
                text = lines.join('\n');
            } else {
                const lines = getSortedExtractedLines(extractResult);
                text = lines.map(line =>
                    line.map(item => `${item.name}: ${item.value}`).join('   ')
                ).join('\n');
            }
            
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    showNotification('已复制所有内容');
                }).catch(() => {
                    alert('复制失败');
                });
            } else {
                const textArea = document.createElement("textarea");
                textArea.value = text;
                textArea.style.position = "fixed";
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                try {
                    document.execCommand('copy');
                    showNotification('已复制所有内容');
                } catch (err) {
                    alert('复制失败');
                }
                document.body.removeChild(textArea);
            }
        }

        // ==================== 工具函数 ====================
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function downloadFile(content, filename, type) {
            const blob = new Blob([content], { type: type });
            
            if (window.navigator && window.navigator.msSaveOrOpenBlob) {
                window.navigator.msSaveOrOpenBlob(blob, filename);
            } else {
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = filename;
                link.style.display = 'none';
                // 移除 target='_blank' 和 rel='noopener noreferrer'，这在某些浏览器中可能会导致下载失败或打开新页面而不是下载
                document.body.appendChild(link);
                link.click();
                setTimeout(() => {
                    document.body.removeChild(link);
                    URL.revokeObjectURL(link.href);
                }, 100);
            }
        }
    