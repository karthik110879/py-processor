#!/usr/bin/env node
/**
 * TypeScript/JavaScript AST Editor using ts-morph
 * 
 * Accepts JSON input via stdin:
 * {
 *   "content": string,
 *   "changes": string[],
 *   "filePath": string
 * }
 * 
 * Returns JSON via stdout:
 * {
 *   "success": boolean,
 *   "content": string,
 *   "error"?: string
 * }
 */

const fs = require('fs');
const path = require('path');

// Read input from stdin
let inputData = '';
process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
    inputData += chunk;
});

process.stdin.on('end', () => {
    try {
        const input = JSON.parse(inputData);
        const result = applyEdits(input.content, input.changes, input.filePath);
        console.log(JSON.stringify(result));
    } catch (error) {
        console.log(JSON.stringify({
            success: false,
            content: '',
            error: error.message
        }));
        process.exit(1);
    }
});

/**
 * Apply edits to TypeScript/JavaScript code using ts-morph
 */
function applyEdits(content, changes, filePath) {
    try {
        // Check if ts-morph is available
        // Node.js automatically checks NODE_PATH environment variable when set
        // We also try require.resolve as a fallback to find ts-morph in other locations
        let tsMorph;
        try {
            tsMorph = require('ts-morph');
        } catch (e) {
            // Fallback: try using require.resolve to find ts-morph
            // This will search node_modules in current directory and parent directories
            try {
                const tsMorphPath = require.resolve('ts-morph');
                // require.resolve found it, so we can require it directly
                // The path returned is to the main entry point, so we can require it
                tsMorph = require(tsMorphPath);
            } catch (resolveError) {
                return {
                    success: false,
                    content: content,
                    error: 'ts-morph not available. Install with: npm install ts-morph (or install in py-processor project root)'
                };
            }
        }

        // Determine file extension
        const ext = path.extname(filePath).toLowerCase();
        const isTypeScript = ext === '.ts' || ext === '.tsx';
        const isJavaScript = ext === '.js' || ext === '.jsx';

        if (!isTypeScript && !isJavaScript) {
            return {
                success: false,
                content: content,
                error: `Unsupported file type: ${ext}`
            };
        }

        // Create project
        const project = new tsMorph.Project({
            useInMemoryFileSystem: true
        });

        // Create source file
        const sourceFile = project.createSourceFile(filePath, content, {
            overwrite: true
        });

        // Apply changes
        for (const change of changes) {
            const changeLower = change.toLowerCase();
            
            // Handle import additions
            if (changeLower.includes('add import') || changeLower.includes('import')) {
                applyImportChange(sourceFile, change);
            }
            // Handle method/function additions
            else if (changeLower.includes('add method') || changeLower.includes('add function')) {
                applyMethodChange(sourceFile, change);
            }
            // Handle modifications
            else if (changeLower.includes('modify') || changeLower.includes('change') ||
                     changeLower.includes('add button') || changeLower.includes('add back') ||
                     changeLower.includes('add prop') || changeLower.includes('add state') ||
                     changeLower.includes('add navigation') || changeLower.includes('add route')) {
                applyModification(sourceFile, change, filePath);
            }
        }

        // Get modified content
        const modifiedContent = sourceFile.getFullText();

        return {
            success: true,
            content: modifiedContent
        };

    } catch (error) {
        return {
            success: false,
            content: content,
            error: error.message
        };
    }
}

/**
 * Apply import-related changes
 */
function applyImportChange(sourceFile, change) {
    const tsMorph = require('ts-morph');
    
    // Check if import already exists
    const existingImports = sourceFile.getImportDeclarations();
    
    // Parse import statement from change description
    // Examples:
    // - "Add import X from Y"
    // - "Import X from Y"
    // - "Add import { X, Y } from 'module'"
    
    let importMatch;
    
    // Try to match "from 'module'" pattern
    const fromMatch = change.match(/from\s+['"]([^'"]+)['"]/i);
    if (fromMatch) {
        const moduleName = fromMatch[1];
        
        // Check if import already exists
        const alreadyImported = existingImports.some(imp => {
            const moduleSpecifier = imp.getModuleSpecifierValue();
            return moduleSpecifier === moduleName;
        });
        
        if (alreadyImported) {
            return; // Import already exists
        }
        
        // Extract import names
        const importNamesMatch = change.match(/(?:import|add import)\s+{([^}]+)}/i);
        if (importNamesMatch) {
            // Named imports: { X, Y }
            const names = importNamesMatch[1].split(',').map(n => n.trim());
            const importSpecifiers = names.map(name => {
                return {
                    name: name
                };
            });
            
            sourceFile.addImportDeclaration({
                moduleSpecifier: moduleName,
                namedImports: importSpecifiers
            });
        } else {
            // Default import or import *
            const defaultImportMatch = change.match(/(?:import|add import)\s+(\w+)/i);
            if (defaultImportMatch) {
                const defaultName = defaultImportMatch[1];
                sourceFile.addImportDeclaration({
                    moduleSpecifier: moduleName,
                    defaultImport: defaultName
                });
            } else {
                // Import everything
                sourceFile.addImportDeclaration({
                    moduleSpecifier: moduleName,
                    namespaceImport: '*'
                });
            }
        }
    } else {
        // Try simple "import X" pattern
        const simpleImportMatch = change.match(/(?:import|add import)\s+(\w+)/i);
        if (simpleImportMatch) {
            const importName = simpleImportMatch[1];
            
            // Check if already imported
            const alreadyImported = existingImports.some(imp => {
                const namedImports = imp.getNamedImports();
                return namedImports.some(ni => ni.getName() === importName);
            });
            
            if (!alreadyImported) {
                // For simple imports, we need a module name
                // This is a limitation - we'd need more context
                // For now, skip or use a default pattern
                console.warn(`Cannot determine module for import: ${importName}`);
            }
        }
    }
}

/**
 * Apply method/function-related changes
 */
function applyMethodChange(sourceFile, change) {
    const tsMorph = require('ts-morph');
    
    // Extract method/function name from change description
    // Examples:
    // - "Add method myMethod"
    // - "Add function processData"
    
    const methodMatch = change.match(/(?:add|create)\s+(?:method|function)\s+(\w+)/i);
    if (!methodMatch) {
        return; // Cannot parse method name
    }
    
    const methodName = methodMatch[1];
    
    // Check if method already exists
    const classes = sourceFile.getClasses();
    for (const cls of classes) {
        const existingMethod = cls.getMethod(methodName);
        if (existingMethod) {
            return; // Method already exists
        }
    }
    
    // Check functions at file level
    const functions = sourceFile.getFunctions();
    for (const func of functions) {
        if (func.getName() === methodName) {
            return; // Function already exists
        }
    }
    
    // Add method to first class found, or as top-level function
    if (classes.length > 0) {
        const firstClass = classes[0];
        firstClass.addMethod({
            name: methodName,
            returnType: 'void',
            statements: [
                '// TODO: Implement method'
            ]
        });
    } else {
        // Add as top-level function
        sourceFile.addFunction({
            name: methodName,
            returnType: 'void',
            statements: [
                '// TODO: Implement function'
            ]
        });
    }
}

/**
 * Detect framework from file content
 */
function detectFrameworkFromContent(content, filePath) {
    const ext = path.extname(filePath).toLowerCase();
    const contentLower = content.toLowerCase();
    
    // Check for Angular patterns
    if (content.includes('@Component') || 
        content.includes('@NgModule') || 
        content.includes('@angular/core') ||
        content.includes('@angular/common') ||
        content.includes('@angular/router')) {
        return 'angular';
    }
    
    // Check for React patterns
    if (content.includes('import React') || 
        content.includes('from \'react\'') ||
        content.includes('from "react"') ||
        content.includes('useState') ||
        content.includes('useEffect') ||
        content.includes('useNavigate') ||
        (ext === '.tsx' && content.includes('return ('))) {
        return 'react';
    }
    
    // Check for Vue patterns
    if (ext === '.vue' ||
        content.includes('defineComponent') ||
        content.includes('from \'vue\'') ||
        content.includes('from "vue"') ||
        content.includes('<template>')) {
        return 'vue';
    }
    
    // Check for Next.js patterns
    if (content.includes('next/router') ||
        content.includes('next/link') ||
        content.includes('next/navigation') ||
        content.includes('useRouter') && content.includes('next')) {
        return 'nextjs';
    }
    
    // Default based on extension
    if (ext === '.tsx') {
        return 'react'; // Most likely React if .tsx
    }
    
    return null;
}

/**
 * Generate React button component
 */
function generateReactButton(buttonText, onClickHandler, sourceFile) {
    const tsMorph = require('ts-morph');
    
    // Check if React is imported
    const imports = sourceFile.getImportDeclarations();
    const hasReact = imports.some(imp => {
        const specifier = imp.getModuleSpecifierValue();
        return specifier === 'react' || specifier === 'react-dom';
    });
    
    if (!hasReact) {
        sourceFile.addImportDeclaration({
            moduleSpecifier: 'react',
            defaultImport: 'React'
        });
    }
    
    // Generate JSX button code
    const buttonCode = `<button onClick={${onClickHandler}}>${buttonText}</button>`;
    return buttonCode;
}

/**
 * Generate Angular button template
 */
function generateAngularButton(buttonText, clickHandler, sourceFile) {
    // Angular buttons are typically in template files, but we can add the handler method
    const classes = sourceFile.getClasses();
    if (classes.length > 0) {
        const componentClass = classes[0];
        const methodName = clickHandler || 'onButtonClick';
        
        // Check if method already exists
        const existingMethod = componentClass.getMethod(methodName);
        if (!existingMethod) {
            componentClass.addMethod({
                name: methodName,
                returnType: 'void',
                statements: [
                    `// Handle ${buttonText} button click`
                ]
            });
        }
    }
    
    // Return template code (would be used in .html file)
    return `<button (click)="${clickHandler || 'onButtonClick'}()">${buttonText}</button>`;
}

/**
 * Generate Vue button template
 */
function generateVueButton(buttonText, clickHandler, sourceFile) {
    // Vue buttons are in template, but we can add the method
    const functions = sourceFile.getFunctions();
    const classes = sourceFile.getClasses();
    
    const methodName = clickHandler || 'onButtonClick';
    
    // Check if method exists
    let methodExists = false;
    for (const func of functions) {
        if (func.getName() === methodName) {
            methodExists = true;
            break;
        }
    }
    
    if (!methodExists && classes.length > 0) {
        classes[0].addMethod({
            name: methodName,
            returnType: 'void',
            statements: [
                `// Handle ${buttonText} button click`
            ]
        });
    }
    
    // Return template code
    return `<button @click="${clickHandler || 'onButtonClick'}">${buttonText}</button>`;
}

/**
 * Generate back button based on framework
 */
function generateBackButton(framework, sourceFile) {
    const tsMorph = require('ts-morph');
    
    if (framework === 'react') {
        // Check for React Router imports
        const imports = sourceFile.getImportDeclarations();
        const hasRouter = imports.some(imp => {
            const specifier = imp.getModuleSpecifierValue();
            return specifier === 'react-router-dom' || specifier === 'next/navigation';
        });
        
        if (!hasRouter) {
            // Try to detect Next.js vs React Router
            const content = sourceFile.getFullText();
            if (content.includes('next/navigation') || content.includes('next/router')) {
                sourceFile.addImportDeclaration({
                    moduleSpecifier: 'next/navigation',
                    namedImports: [{ name: 'useRouter' }]
                });
                
                // Add hook usage in component
                return {
                    import: 'useRouter from next/navigation',
                    code: `const router = useRouter();\nconst handleBack = () => router.back();`,
                    jsx: '<button onClick={handleBack}>Back</button>'
                };
            } else {
                sourceFile.addImportDeclaration({
                    moduleSpecifier: 'react-router-dom',
                    namedImports: [{ name: 'useNavigate' }]
                });
                
                return {
                    import: 'useNavigate from react-router-dom',
                    code: `const navigate = useNavigate();\nconst handleBack = () => navigate(-1);`,
                    jsx: '<button onClick={handleBack}>Back</button>'
                };
            }
        }
        
        return {
            code: 'const handleBack = () => window.history.back();',
            jsx: '<button onClick={handleBack}>Back</button>'
        };
    } else if (framework === 'angular') {
        // Check for Router import
        const imports = sourceFile.getImportDeclarations();
        const hasRouter = imports.some(imp => {
            const specifier = imp.getModuleSpecifierValue();
            return specifier === '@angular/router';
        });
        
        if (!hasRouter) {
            sourceFile.addImportDeclaration({
                moduleSpecifier: '@angular/router',
                namedImports: [{ name: 'Router' }]
            });
        }
        
        // Add method to component class
        const classes = sourceFile.getClasses();
        if (classes.length > 0) {
            const componentClass = classes[0];
            const existingMethod = componentClass.getMethod('goBack');
            if (!existingMethod) {
                // Check if Router is injected in constructor
                const constructors = componentClass.getConstructors();
                let hasRouterParam = false;
                if (constructors.length > 0) {
                    const params = constructors[0].getParameters();
                    hasRouterParam = params.some(p => {
                        const type = p.getType();
                        return type && type.getText().includes('Router');
                    });
                }
                
                if (!hasRouterParam && constructors.length > 0) {
                    // Add Router to constructor
                    constructors[0].addParameter({
                        name: 'router',
                        type: 'Router',
                        scope: 'private'
                    });
                } else if (constructors.length === 0) {
                    // Add constructor with Router
                    componentClass.addConstructor({
                        parameters: [{
                            name: 'router',
                            type: 'Router',
                            scope: 'private'
                        }]
                    });
                }
                
                componentClass.addMethod({
                    name: 'goBack',
                    returnType: 'void',
                    statements: [
                        'this.router.navigate(["/"]); // Or use this.location.back() if Location service is preferred'
                    ]
                });
            }
        }
        
        return {
            template: '<button (click)="goBack()">Back</button>',
            method: 'goBack() method added to component'
        };
    } else if (framework === 'vue') {
        // Check for router import
        const imports = sourceFile.getImportDeclarations();
        const hasRouter = imports.some(imp => {
            const specifier = imp.getModuleSpecifierValue();
            return specifier === 'vue-router';
        });
        
        if (!hasRouter) {
            sourceFile.addImportDeclaration({
                moduleSpecifier: 'vue-router',
                namedImports: [{ name: 'useRouter' }]
            });
        }
        
        return {
            code: 'const router = useRouter();\nconst goBack = () => router.back();',
            template: '<button @click="goBack">Back</button>'
        };
    }
    
    // Fallback
    return {
        code: 'const goBack = () => window.history.back();',
        template: '<button onClick={goBack}>Back</button>'
    };
}

/**
 * Apply general modifications with framework awareness
 */
function applyModification(sourceFile, change, filePath) {
    const tsMorph = require('ts-morph');
    const content = sourceFile.getFullText();
    const framework = detectFrameworkFromContent(content, filePath);
    const changeLower = change.toLowerCase();
    
    // Handle UI element additions
    if (changeLower.includes('add button') || changeLower.includes('add back button')) {
        // Extract button text if specified
        const buttonTextMatch = change.match(/button[:\s]+([^,\.]+)/i);
        const buttonText = buttonTextMatch ? buttonTextMatch[1].trim() : 'Button';
        
        if (changeLower.includes('back button') || changeLower.includes('back')) {
            const backButton = generateBackButton(framework, sourceFile);
            
            // For React, we need to add the code to the component
            if (framework === 'react') {
                // Find the component function/class
                const functions = sourceFile.getFunctions();
                const classes = sourceFile.getClasses();
                
                // Try to find the main component
                let targetComponent = null;
                for (const func of functions) {
                    if (func.getName() && func.getName()[0] === func.getName()[0].toUpperCase()) {
                        targetComponent = func;
                        break;
                    }
                }
                
                if (targetComponent && backButton.code) {
                    // Add the code before the return statement
                    const body = targetComponent.getBody();
                    if (body) {
                        const statements = body.getStatements();
                        // Find return statement
                        let returnIndex = -1;
                        for (let i = 0; i < statements.length; i++) {
                            if (statements[i].getKindName() === 'ReturnStatement') {
                                returnIndex = i;
                                break;
                            }
                        }
                        
                        if (returnIndex > 0) {
                            // Insert before return
                            const codeLines = backButton.code.split('\n');
                            for (let i = codeLines.length - 1; i >= 0; i--) {
                                body.insertStatements(returnIndex, codeLines[i]);
                            }
                        }
                    }
                }
            }
            
            // Log what was generated
            console.log(`Generated back button for ${framework || 'unknown'} framework`);
            return;
        } else {
            // Regular button
            const onClickMatch = change.match(/onclick[:\s]+([^,\.]+)/i);
            const onClickHandler = onClickMatch ? onClickMatch[1].trim() : 'handleClick';
            
            if (framework === 'react') {
                generateReactButton(buttonText, onClickHandler, sourceFile);
            } else if (framework === 'angular') {
                generateAngularButton(buttonText, onClickHandler, sourceFile);
            } else if (framework === 'vue') {
                generateVueButton(buttonText, onClickHandler, sourceFile);
            }
            return;
        }
    }
    
    // Handle component modifications (props, state, methods)
    if (changeLower.includes('add prop') || changeLower.includes('add property')) {
        const propMatch = change.match(/(?:add|create)\s+(?:prop|property)[:\s]+(\w+)/i);
        if (propMatch) {
            const propName = propMatch[1];
            
            if (framework === 'react') {
                // Add to component props interface or function parameters
                const interfaces = sourceFile.getInterfaces();
                let propsInterface = null;
                for (const intf of interfaces) {
                    if (intf.getName().includes('Props') || intf.getName().includes('props')) {
                        propsInterface = intf;
                        break;
                    }
                }
                
                if (propsInterface) {
                    propsInterface.addProperty({
                        name: propName,
                        type: 'any'
                    });
                }
            } else if (framework === 'angular') {
                // Add as @Input() property
                const classes = sourceFile.getClasses();
                if (classes.length > 0) {
                    const componentClass = classes[0];
                    // Check if @Input is imported
                    const imports = sourceFile.getImportDeclarations();
                    const hasInput = imports.some(imp => {
                        const namedImports = imp.getNamedImports();
                        return namedImports.some(ni => ni.getName() === 'Input');
                    });
                    
                    if (!hasInput) {
                        sourceFile.addImportDeclaration({
                            moduleSpecifier: '@angular/core',
                            namedImports: [{ name: 'Input' }]
                        });
                    }
                    
                    componentClass.addProperty({
                        name: propName,
                        type: 'any',
                        decorators: [{
                            name: 'Input',
                            arguments: []
                        }]
                    });
                }
            }
            return;
        }
    }
    
    // Handle state additions (React hooks)
    if (changeLower.includes('add state') || changeLower.includes('use state')) {
        const stateMatch = change.match(/(?:add|create)\s+state[:\s]+(\w+)/i);
        if (stateMatch && framework === 'react') {
            const stateName = stateMatch[1];
            
            // Check if useState is imported
            const imports = sourceFile.getImportDeclarations();
            const hasUseState = imports.some(imp => {
                const specifier = imp.getModuleSpecifierValue();
                if (specifier === 'react') {
                    const namedImports = imp.getNamedImports();
                    return namedImports.some(ni => ni.getName() === 'useState');
                }
                return false;
            });
            
            if (!hasUseState) {
                // Add useState to React import
                const reactImport = imports.find(imp => imp.getModuleSpecifierValue() === 'react');
                if (reactImport) {
                    reactImport.addNamedImport('useState');
                } else {
                    sourceFile.addImportDeclaration({
                        moduleSpecifier: 'react',
                        namedImports: [{ name: 'useState' }]
                    });
                }
            }
            
            // Add useState hook to component
            const functions = sourceFile.getFunctions();
            for (const func of functions) {
                if (func.getName() && func.getName()[0] === func.getName()[0].toUpperCase()) {
                    const body = func.getBody();
                    if (body) {
                        const statements = body.getStatements();
                        // Insert at the beginning
                        body.insertStatements(0, `const [${stateName}, set${stateName.charAt(0).toUpperCase() + stateName.slice(1)}] = useState();`);
                        return;
                    }
                }
            }
        }
    }
    
    // Handle navigation/routing additions
    if (changeLower.includes('add navigation') || changeLower.includes('add route') || changeLower.includes('add routing')) {
        if (framework === 'react') {
            // Already handled in generateBackButton for React Router
            generateBackButton('react', sourceFile);
        } else if (framework === 'angular') {
            // Router is typically injected, already handled
            generateBackButton('angular', sourceFile);
        } else if (framework === 'vue') {
            generateBackButton('vue', sourceFile);
        }
        return;
    }
    
    // If no specific pattern matched, log warning
    console.warn(`Modification pattern not fully handled: ${change} (Framework: ${framework || 'unknown'})`);
}
