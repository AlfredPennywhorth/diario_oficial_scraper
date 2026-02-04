import shutil
import os

def create_zip():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(base_dir, 'dist')
    source_dir = os.path.join(dist_dir, 'DiarioScraper')
    output_filename = os.path.join(dist_dir, 'DiarioScraper')
    
    if not os.path.exists(source_dir):
        print(f"Erro: O diretório fonte não existe: {source_dir}")
        return

    print(f"Compactando '{source_dir}' para '{output_filename}.zip'...")
    shutil.make_archive(output_filename, 'zip', root_dir=dist_dir, base_dir='DiarioScraper')
    print("Concluído com sucesso!")

if __name__ == "__main__":
    create_zip()
